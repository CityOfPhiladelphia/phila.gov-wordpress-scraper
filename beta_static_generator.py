import os
import re
import sys
import json
import time
import hashlib
import smtplib
import logging
import threading
from logging.config import dictConfig
from email.mime.text import MIMEText
from queue import PriorityQueue

import requests
import boto3
import botocore
import click

with open('config.json') as file:
    config = json.load(file)

SAVE_FOLDER = config["save_folder"]
NEW_BASE_URL = config["new_base_url"]
API_URL = config["api"]

HEADER = {'user-agent': 'beta-static-generator/0.0.1'}

THREAD_ERROR = False
STATS = {
    'pages_scraped': 0,
    'pages_updated': 0,
    'pages_new': 0
}

def init_logger(logging_config):
    try:
        with open(logging_config) as file:
            config = yaml.load(file)
        dictConfig(config)
    except:
        FORMAT = '[%(asctime)-15s] %(levelname)s [%(name)s] %(message)s'
        logging.basicConfig(format=FORMAT, level=logging.INFO, stream=sys.stderr)

    logger = logging.getLogger('beta-static-generator')

    def exception_handler(type, value, tb):
        logger.exception("Uncaught exception: {}".format(str(value)), exc_info=(type, value, tb))

    sys.excepthook = exception_handler

    return logger

def save_page(logger, session, url, host_to_replace, save_s3, s3_client, s3_bucket):
    logger.info('Scraping: {}'.format(url))
    response = session.get(url, headers=HEADER)
    key = SAVE_FOLDER + url.replace('https://{}/'.format(host_to_replace), '')
    if key.endswith('/'):
        key += 'index.html'
    content_type_list = response.headers['Content-Type'].split(';')
    content_type = content_type_list[0]

    if content_type == 'text/html':
        body = re.sub('(https?://)?{}'.format(host_to_replace),
                      NEW_BASE_URL,
                      response.text).encode('utf-8')
    else:
        body = response.content

    page_updated = False
    page_new = False

    if save_s3:
        if content_type == 'text/html':
            md_body = re.sub(r'"nonce":"[a-f0-9]{10}"', '', body.decode('utf-8')).encode('utf-8')
        else:
            md_body = body

        m = hashlib.md5()
        m.update(md_body)
        md5 = m.hexdigest()

        try:
            response = s3_client.head_object(Bucket=s3_bucket,
                                             Key=key)
            s3_md5 = response['Metadata'].get('scraper_md5',
                                              response['ETag'].replace('"', ''))
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                s3_md5 = None
            else:
                raise

        if s3_md5 is None or md5 != s3_md5:
            if md5 and s3_md5:
                page_updated = True
                logger.info('Page update: {}, source: {}, s3: {}'.format(
                    key,
                    md5,
                    s3_md5))
            else:
                page_new = True
                logger.info('New Page: {}, source: {}'.format(
                    key,
                    md5))
            s3_client.put_object(Bucket=s3_bucket,
                                 Key=key,
                                 Body=body,
                                 ContentType=content_type,
                                 ACL='public-read',
                                 Metadata={
                                    'scraper_md5': md5
                                })
            ## TODO: invalidate CloudFront?
        else:
            logger.info('Page not updated: {}, source: {}, s3: {}'.format(
                    key,
                    md5,
                    s3_md5))
    else:
        ## TODO: add md5 check?
        path = os.path.join(os.getcwd(), key)
        if not os.path.exists(os.path.dirname(path)):
            try:
                os.makedirs(os.path.dirname(path))
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

        with open(path, 'wb') as file:
            file.write(body)

        page_new = True

    return page_new, page_updated

def get_pages_list(url):
    response = requests.get(url, headers=HEADER)
    data = response.json()
    return data

def send_error_email(orig_error, e):
    try:
        subject = "Beta generator encountered an error when building the site"
        body = 'Original Error: {}\n\nSlack error details: {}'.format(orig_error, str(e))
        msg = MIMEText(subject + body)
        msg['Subject'] = subject
        msg['From'] = 'ithelp@phila.gov'
        msg['To'] = 'andrew.kennel@phila.gov'
        send_email(msg)
    except:
        logger.exception('Exception sending error email')

def post_to_slack(message):
    post = {"text": "{0}".format(message)}
    
    try:
        requests.post('https://hooks.slack.com/services/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',
                      json=post)
    except Exception as em:
        #Fall-back to sending an email
        logger.exception('Exception sending error message to Slack')
        send_error_email(message, em)

def send_email(msg):
    s = smtplib.SMTP("relay.city.phila.local")
    s.set_debuglevel(1)
    s.send_message(msg)
    s.quit()

def stop_workers(q, threads):
    for i in range(len(threads)):
        q.put((1, None))
    for t in threads:
        t.join()

@click.command()
@click.option('--save-s3', is_flag=True, default=False, help='Save site to S3 bucket.')
@click.option('--logging-config', default='logging_config.conf', help='Python logging config file in YAML format.')
@click.option('--num-worker-threads', type=int, default=12, help='Number of workers.')
@click.option('--notifications/--no-notifications', is_flag=True, default=False, help='Enable Slack/email error notifications.')
@click.option('--publish-stats/--no-publish-stats', is_flag=True, default=False, help='Publish stats to Cloudwatch')
@click.option('--heartbeat/--no-heartbeat', is_flag=True, default=False, help='Cloudwatch hearbeat')
def main(save_s3, logging_config, num_worker_threads, notifications, heartbeat, publish_stats):
    global THREAD_ERROR

    cloudwatch_client = boto3.client('cloudwatch')

    logger = init_logger(logging_config)

    host_to_replace = config.get('host_to_replace')

    logger.info('Starting scraper')

    q = PriorityQueue()
    stats_lock = threading.Lock()
    error_lock = threading.Lock()

    def worker():
        global THREAD_ERROR, STATS

        session = requests.Session()
        s3_client = None
        s3_bucket = config.get('s3_bucket')

        if save_s3:
            try:
                time.sleep(0.1) # Rate limits acquiring creds in so many threads
                s3_client = boto3.client('s3')
            except Exception as e:
                message = 'Exception creating S3 client in thread'
                logger.exception(message)
                with error_lock:
                    THREAD_ERROR = message
                raise e

        while THREAD_ERROR is False:
            priority, url = q.get()
            if url is None:
                break
            try:
                page_new, page_updated = save_page(logger,
                                                   session,
                                                   url,
                                                   host_to_replace,
                                                   save_s3,
                                                   s3_client,
                                                   s3_bucket)
                with stats_lock:
                    STATS['pages_scraped'] += 1
                    if page_new:
                        STATS['pages_new'] += 1
                    if page_updated:
                        STATS['pages_updated'] += 1
            except Exception as e:
                message = 'Exception scraping: {}'.format(url)
                logger.exception(message)
                with error_lock:
                    THREAD_ERROR = message
                raise e
            q.task_done()

    threads = []
    for i in range(num_worker_threads):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    try:
        logger.info('Scraping static files')
        static_pages = open('staticfiles.csv','r').read().splitlines()
        for url in static_pages:
            url = 'https://{}{}'.format(host_to_replace, url)
            q.put((3, url))

        max_datetime = '2000-01-01 00:00:00'
        max_url = None
        logger.info('Fetching page list from: {}'.format(API_URL))
        page_data = get_pages_list(API_URL)
        for page in page_data:
            if page['updated_at'] > max_datetime:
                max_datetime = page['updated_at']
                max_url = page["link"]
            q.put((3, page["link"]))
        
        last_url = None
        while True:
            if q.empty() or THREAD_ERROR is not False:
                break

            logger.info('Fetching pages updated since: %s', max_datetime)
            page_data = get_pages_list(API_URL + '?timestamp=' + max_datetime)
            for page in page_data:
                # Often just the most recent page is returned, we don't want to just keep scraping it
                if page['updated_at'] == max_datetime and page["link"] == max_url:
                    continue
                if page['updated_at'] > max_datetime:
                    max_datetime = page['updated_at']
                    max_url = page["link"]
                q.put((2, page["link"]))

            time.sleep(1)

        stop_workers(q, threads)

        if THREAD_ERROR is not False:
            raise Exception(THREAD_ERROR)

        logger.info('Stats - Pages Scraped: {}, Pages New: {}, Pages Updated: {}'.format(
            STATS['pages_scraped'],
            STATS['pages_new'],
            STATS['pages_updated']))

        if publish_stats:
            try:
                stats_config = config.get('cloudwatch', {}).get('stats')
                metrics_prefix = stats_config.get('metrics_prefix', '')
                cloudwatch_client.put_metric_data(
                    Namespace=stats_config.get('namespace'),
                    MetricData=[
                        {
                            'MetricName': metrics_prefix + 'pages-scraped',
                            'Value': STATS['pages_scraped'],
                            'Unit': 'Count'
                        },
                        {
                            'MetricName': metrics_prefix + 'pages-new',
                            'Value': STATS['pages_new'],
                            'Unit': 'Count'
                        },
                        {
                            'MetricName': metrics_prefix + 'pages-updated',
                            'Value': STATS['pages_updated'],
                            'Unit': 'Count'
                        }
                    ])
            except:
                logger.exception('Exception publishing stats to Cloudwatch')
                raise
    except Exception as e:
        logger.exception('Exception occured scraping site')
        with error_lock:
            THREAD_ERROR = 'Exception occured scraping site'
        stop_workers(q, threads)
        if notifications:
            post_to_slack('Exception occured scraping site: ' + str(e))

    if heartbeat:
        try:
            heartbeat_config = config.get('cloudwatch', {}).get('heartbeat')
            cloudwatch_client.put_metric_data(
                Namespace=heartbeat_config.get('namespace'),
                MetricData=[
                    {
                        'MetricName': heartbeat_config.get('metric'),
                        'Value': 1,
                        'Unit': 'Count'
                    }
                ])
        except:
            logger.exception('Exception sending heartbeat to Cloudwatch')
            raise

if __name__ == '__main__':
    main()
