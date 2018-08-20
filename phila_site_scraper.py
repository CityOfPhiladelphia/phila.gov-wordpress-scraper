import os
import re
import sys
import json
import time
import uuid
import signal
import hashlib
import smtplib
import logging
import threading
from urllib.parse import urlparse
from logging.config import dictConfig
from email.mime.text import MIMEText
from queue import PriorityQueue
from datetime import datetime

import requests
import boto3
import botocore
import click
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from slack_logger import SlackHandler, SlackFormatter, SlackLogFilter

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

SCRAPER_SLACK_URL = os.getenv('SCRAPER_SLACK_URL')
SCRAPER_HOSTNAMES_TO_FIND = os.getenv('SCRAPER_HOSTNAMES_TO_FIND')
SCRAPER_HOSTNAME_REPLACE = os.getenv('SCRAPER_HOSTNAME_REPLACE')
SCRAPER_HOST_FOR_URLS_AND_PAGES = os.getenv('SCRAPER_HOST_FOR_URLS_AND_PAGES')
SCRAPER_S3_BUCKET = os.getenv('SCRAPER_S3_BUCKET')
SCRAPER_CLOUDFRONT_DISTRIBUTION = os.getenv('SCRAPER_CLOUDFRONT_DISTRIBUTION')
SCRAPER_CLOUDFRONT_MAX_INVALIDATIONS = int(os.getenv('SCRAPER_CLOUDFRONT_MAX_INVALIDATIONS', 50))
SCRAPER_CLOUDFRONT_CLOUDWATCH_NAMESPACE = os.getenv('SCRAPER_CLOUDFRONT_CLOUDWATCH_NAMESPACE')

HEADER = {'user-agent': 'beta-static-generator/0.0.1'}

THREAD_ERROR = False
STATS = {
    'pages_scraped': 0,
    'pages_updated': 0,
    'pages_new': 0,
    'invalidations': 0,
    'updated_at_pages': 0
}

def init_logger(logging_config, run_id):
    try:
        with open(logging_config) as file:
            config = yaml.load(file)
        dictConfig(config)
    except:
        FORMAT = '[' + run_id + '] [%(asctime)-15s] %(levelname)s [%(name)s] %(message)s'
        logging.basicConfig(format=FORMAT, level=logging.INFO, stream=sys.stderr)

    logger = logging.getLogger('beta-static-generator')

    slack_handler = SlackHandler(SCRAPER_SLACK_URL)
    slack_filter = SlackLogFilter()
    slack_handler.addFilter(slack_filter)
    slack_handler.setFormatter(SlackFormatter())
    logger.addHandler(slack_handler)

    def exception_handler(type, value, tb):
        logger.exception("Uncaught exception: {}".format(str(value)), exc_info=(type, value, tb))

    sys.excepthook = exception_handler

    return logger

def save_page(logger,
              session,
              url,
              updated_at,
              save_s3,
              invalidate_cloudfront,
              s3_client,
              cloudfront_client):
    logger.info('Scraping: {}'.format(url))
    response = session.get(url, headers=HEADER, verify=False)

    key = urlparse(url).path[1:]
    if key == '':
        key = 'index.html'
    elif '.' not in key:
        if not key.endswith('/'):
            key += '/'
        key += 'index.html'

    original_content_type = response.headers['Content-Type']
    content_type_list = original_content_type.split(';')
    content_type = content_type_list[0]

    if content_type == 'text/html':
        body = re.sub(SCRAPER_HOSTNAMES_TO_FIND,
                      SCRAPER_HOSTNAME_REPLACE,
                      response.text).encode('utf-8')
    else:
        body = response.content

    page_updated = False
    page_new = False
    invalidation = False

    if save_s3:
        if content_type == 'text/html':
            md_body = re.sub(r'"nonce":"[a-f0-9]{10}"', '', body.decode('utf-8')).encode('utf-8')
        else:   
            md_body = body

        m = hashlib.md5()
        m.update(md_body)
        md5 = m.hexdigest()

        try:
            response = s3_client.head_object(Bucket=SCRAPER_S3_BUCKET,
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
            s3_client.put_object(Bucket=SCRAPER_S3_BUCKET,
                                 Key=key,
                                 Body=body,
                                 ContentType=original_content_type,
                                 ACL='public-read',
                                 Metadata={
                                    'scraper_md5': md5
                                 })
            if page_updated and invalidate_cloudfront:
                num_invalidations = STATS['invalidations']
                if num_invalidations < SCRAPER_CLOUDFRONT_MAX_INVALIDATIONS:
                    try:
                        invaldiation_path = key
                        if key[:1] != '/':
                            invaldiation_path = '/' + invaldiation_path
                        cloudfront_client.create_invalidation(
                            DistributionId=SCRAPER_CLOUDFRONT_DISTRIBUTION,
                            InvalidationBatch={
                                'Paths': {
                                    'Quantity': 1,
                                    'Items': [invaldiation_path]
                                },
                                'CallerReference': (updated_at or datetime.utcnow().isoformat()) + invaldiation_path
                            })
                        logger.info('CloudFront Invalidation ({}/{}): {}'.format(
                            num_invalidations + 1,
                            SCRAPER_CLOUDFRONT_MAX_INVALIDATIONS,
                            invaldiation_path))
                        invalidation = True
                    except:
                        logger.exception('Exception invalidating: {}'.format(invaldiation_path))
        else:
            logger.info('Page not updated: {}, source: {}, s3: {}'.format(
                    key,
                    md5,
                    s3_md5))
    else:
        ## TODO: add md5 check?
        key = 'sitefiles/' + key
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

    return page_new, page_updated, invalidation

def get_pages_list(url):
    response = requests.get(url, headers=HEADER, verify=False)
    data = response.json()
    return data

def stop_workers(q, threads):
    for i in range(len(threads)):
        q.put((1, None, None))
    for t in threads:
        t.join()

@click.command()
@click.option('--save-s3', is_flag=True, default=False, help='Save site to S3 bucket.')
@click.option('--invalidate-cloudfront', is_flag=True, default=False, help='Invalidates CloudFront paths that are updated.')
@click.option('--logging-config', default='logging_config.conf', help='Python logging config file in YAML format.')
@click.option('--num-worker-threads', type=int, default=12, help='Number of workers.')
@click.option('--notifications/--no-notifications', is_flag=True, default=False, help='Enable Slack/email error notifications.')
@click.option('--publish-stats/--no-publish-stats', is_flag=True, default=False, help='Publish stats to Cloudwatch')
@click.option('--heartbeat/--no-heartbeat', is_flag=True, default=False, help='Cloudwatch hearbeat')
def main(save_s3, invalidate_cloudfront, logging_config, num_worker_threads, notifications, heartbeat, publish_stats):
    global THREAD_ERROR

    cloudwatch_client = boto3.client('cloudwatch')

    run_id = str(uuid.uuid4())
    logger = init_logger(logging_config, run_id)

    logger.info('Starting scraper')

    q = PriorityQueue()
    stats_lock = threading.Lock()
    error_lock = threading.Lock()

    def worker():
        global THREAD_ERROR, STATS

        session = requests.Session()
        s3_client = None
        cloudfront_client = None

        if save_s3:
            try:
                time.sleep(0.1) # Rate limits acquiring creds in so many threads
                s3_client = boto3.client('s3')
                cloudfront_client = boto3.client('cloudfront')
            except Exception as e:
                message = 'Exception creating S3 client in thread'
                logger.exception(message)
                with error_lock:
                    THREAD_ERROR = message
                raise e

        while THREAD_ERROR is False:
            priority, url, updated_at = q.get()
            if url is None:
                break
            try:
                page_new, page_updated, invalidation = save_page(logger,
                                                                 session,
                                                                 url,
                                                                 updated_at,
                                                                 save_s3,
                                                                 invalidate_cloudfront,
                                                                 s3_client,
                                                                 cloudfront_client)
                with stats_lock:
                    STATS['pages_scraped'] += 1
                    if page_new:
                        STATS['pages_new'] += 1
                    if page_updated:
                        STATS['pages_updated'] += 1
                    if invalidation:
                        STATS['invalidations'] += 1
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

    def kill(signum, frame):
        stop_workers(q, threads)
        sys.exit(0)
    signal.signal(signal.SIGINT, kill)
    signal.signal(signal.SIGTERM, kill)

    try:
        logger.info('Scraping static files')
        static_pages = open('staticfiles.csv','r').read().splitlines()
        for url in static_pages:
            url = 'https://{}{}'.format(SCRAPER_HOST_FOR_URLS_AND_PAGES, url)
            q.put((3, url, None))

        api_url = 'https://{}{}'.format(SCRAPER_HOST_FOR_URLS_AND_PAGES,
                                        '/wp-json/last-updated/v1/all')

        max_datetime = '2000-01-01 00:00:00'
        max_url = None
        logger.info('Fetching page list from: {}'.format(api_url))
        page_data = get_pages_list(api_url)
        for page in page_data:
            url = 'https://{}{}'.format(SCRAPER_HOST_FOR_URLS_AND_PAGES, page['link'])
            if page['updated_at'] > max_datetime:
                max_datetime = page['updated_at']
                max_url = url
            q.put((3, url, page['updated_at']))
        
        last_url = None
        while True:
            if q.empty() or THREAD_ERROR is not False:
                break

            logger.info('Fetching pages updated since: %s', max_datetime)
            page_data = get_pages_list(api_url + '?timestamp=' + max_datetime)
            for page in page_data:
                # Often just the most recent page is returned, we don't want to just keep scraping it
                updated_at = page['updated_at']
                url = 'https://{}{}'.format(SCRAPER_HOST_FOR_URLS_AND_PAGES, page['link'])
                if updated_at == max_datetime and url == max_url:
                    continue
                if updated_at > max_datetime:
                    max_datetime = updated_at
                    max_url = url
                with stats_lock:
                    STATS['updated_at_pages'] += 1
                q.put((2, url, updated_at))

            time.sleep(1)

        stop_workers(q, threads)

        if THREAD_ERROR is not False:
            raise Exception(THREAD_ERROR)

        logger.info('Stats - Pages Scraped: {}, Pages New: {}, Pages Updated: {}, ' +
                    'Updated At Pages: {}, Invalidations: {}'.format(
                        STATS['pages_scraped'],
                        STATS['pages_new'],
                        STATS['pages_updated'],
                        STATS['updated_at_pages'],
                        STATS['invalidations']))

        if publish_stats:
            try:
                cloudwatch_client.put_metric_data(
                    Namespace=SCRAPER_CLOUDFRONT_CLOUDWATCH_NAMESPACE,
                    MetricData=[
                        {
                            'MetricName': 'pages-scraped',
                            'Value': STATS['pages_scraped'],
                            'Unit': 'Count'
                        },
                        {
                            'MetricName': 'pages-new',
                            'Value': STATS['pages_new'],
                            'Unit': 'Count'
                        },
                        {
                            'MetricName': 'pages-updated',
                            'Value': STATS['pages_updated'],
                            'Unit': 'Count'
                        },
                        {
                            'MetricName': 'invalidations',
                            'Value': STATS['invalidations'],
                            'Unit': 'Count'
                        },
                        {
                            'MetricName': 'updated-at-pages',
                            'Value': STATS['updated_at_pages'],
                            'Unit': 'Count'
                        }
                    ])
            except:
                logger.exception('Exception publishing stats to Cloudwatch')
                raise
    except Exception as e:
        logger.exception('Exception occured scraping site', extra={'notify_slack': notifications}) # CLI flag
        with error_lock:
            THREAD_ERROR = 'Exception occured scraping site'
        stop_workers(q, threads)

    if heartbeat:
        try:
            cloudwatch_client.put_metric_data(
                Namespace=SCRAPER_CLOUDFRONT_CLOUDWATCH_NAMESPACE,
                MetricData=[
                    {
                        'MetricName': 'heartbeat',
                        'Value': 1,
                        'Unit': 'Count'
                    }
                ])
        except:
            logger.exception('Exception sending heartbeat to Cloudwatch')
            raise

if __name__ == '__main__':
    main()
