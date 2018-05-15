import os
import re
import sys
import json
import time
import hashlib
import datetime
import smtplib
import logging
import threading
from logging.config import dictConfig
from email.mime.text import MIMEText
from datetime import datetime
from queue import Queue

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

def save_page(logger, url, save_s3, s3_client, s3_bucket):
    logger.info('Scraping: {}'.format(url))
    response = requests.get(url, headers=HEADER)
    key = SAVE_FOLDER + url.replace('https://beta.phila.gov/', '')
    if key.endswith('/'):
        key += 'index.html'
    content_type_list = response.headers['Content-Type'].split(';')
    content_type = content_type_list[0]

    if content_type == 'text/html':
        body = re.sub('(https?://)?beta\.phila\.gov',
                      NEW_BASE_URL,
                      response.text).encode('utf-8')
    else:
        body = response.content

    if save_s3:
        m = hashlib.md5()
        m.update(body)
        md5 = m.hexdigest()

        try:
            response = s3_client.head_object(Bucket=s3_bucket,
                                             Key=key)
            s3_md5 = response['ETag'].replace('"', '')
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                s3_md5 = None
            else:
                raise

        if s3_md5 is None or md5 != s3_md5:
            if md5 and s3_md5:
                logger.info('Page update: {}, source: {}, s3: {}'.format(
                    url,
                    md5,
                    s3_md5))
            else:
                logger.info('New Page: {}, source: {}'.format(
                    url,
                    md5))
            s3_client.put_object(Bucket=s3_bucket,
                                 Key=key,
                                 Body=body,
                                 ContentType=content_type,
                                 ACL='public-read')
        else:
            logger.info('Page not updated: {}, source: {}, s3: {}'.format(
                    url,
                    md5,
                    s3_md5))
    else:
        path = os.path.join(os.getcwd(), key)
        if not os.path.exists(os.path.dirname(path)):
            try:
                os.makedirs(os.path.dirname(path))
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

        with open(path, 'wb') as file:
            file.write(body)

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
        q.put(None)
    for t in threads:
        t.join()

@click.command()
@click.option('--save-s3', is_flag=True, default=False, help='Save site to S3 bucket.')
@click.option('--s3-bucket', default='static.merge.phila.gov', help='When saving to S3, the bucket to use.')
@click.option('--logging-config', default='logging_config.conf', help='Python logging config file in YAML format.')
@click.option('--num-worker-threads', type=int, default=12, help='Number of workers.')
@click.option('--notifications/--no-notifications', is_flag=True, default=False, help='Enable Slack/email error notifications.')
def main(save_s3, s3_bucket, logging_config, num_worker_threads, notifications):
    logger = init_logger(logging_config)

    logger.info('Starting scraper')

    q = Queue()
    error_lock = threading.Lock()

    def worker():
        global THREAD_ERROR

        s3_client = None
        if save_s3:
            try:
                time.sleep(0.1) # Rate limits acquiring creds in so many threads
                s3_client = boto3.client('s3')
            except Exception as e:
                message = 'Exception creating S3 client in thread'
                logger.exception(message)
                error_lock.acquire()
                THREAD_ERROR = message
                error_lock.release()
                raise e

        while THREAD_ERROR is False:
            url = q.get()
            if url is None:
                break
            try:
                save_page(logger, url, save_s3, s3_client, s3_bucket)
            except Exception as e:
                message = 'Exception scraping: {}'.format(url)
                logger.exception(message)
                error_lock.acquire()
                THREAD_ERROR = message
                error_lock.release()
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
            q.put(url)

        logger.info('Fetching page list from: {}'.format(API_URL))
        page_data = get_pages_list(API_URL)
        for page in page_data:
            q.put(page["link"])

        while True:
            if q.empty() or THREAD_ERROR is not False:
                break
            time.sleep(1)

        stop_workers(q, threads)

        if THREAD_ERROR is not False:
            raise Exception(THREAD_ERROR)
    except Exception as e:
        logger.exception('Exception occured scraping site')
        if notifications:
            post_to_slack('Exception occured scraping site: ' + str(e))

if __name__ == '__main__':
    main()
