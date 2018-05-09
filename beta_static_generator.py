import os
import sys
import json
import datetime
import smtplib
import logging
from logging.config import dictConfig
from email.mime.text import MIMEText

import requests
import boto3
import click

config = json.load(open('config.json'))

SAVE_FOLDER = config["save_folder"]
NEW_URL = config["new_url"]
HEADER = {'user-agent': 'beta-static-generator/0.0.1'}
LASTRUN = config["last_run"]
API_URL = config["api"]

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

def save_page(url, save_s3, s3_client, s3_bucket):
    response = requests.get(url, headers = HEADER)
    key = SAVE_FOLDER + url.replace("https://beta.phila.gov/", "")
    if key.endswith('/'):
        key = key + 'index.html'
    __types = response.headers['Content-Type'].split(';')
    __content_type = __types[0]

    if __content_type == 'text/html':
        body = response.text.replace('beta.phila.gov', NEW_URL)
    else:
        body = response.content
    
    if save_s3:
        s3_bucket.put_object(Key=key,
                             Body=body,
                             ContentType=__content_type,
                             ACL='public-read')
    else:
        path = os.path.join(os.getcwd(), key)
        if not os.path.exists(os.path.dirname(path)):
            try:
                os.makedirs(os.path.dirname(path))
            except OSError as exc: # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise
        with open(path, 'w') as file:
            file.write(body)

def get_pages_list(url):
    response = requests.get(url, headers=HEADER)
    data = response.json()
    return data

def send_error_notification(e):
    try:
        subject = "Beta generator encountered an error when building the site"
        body = "Error details: " + str(e)
        msg = MIMEText(subject + body)
        msg['Subject'] = subject
        msg['From'] = 'ithelp@phila.gov'
        msg['To'] = 'andrew.kennel@phila.gov'
        send_email(msg)
    except:
        print("Fail")

def post_to_slack(message):
    post = {"text": "{0}".format(message)}
 
    try:
        json_data = json.dumps(post)
        requests.post("https://hooks.slack.com/services/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",
                              data=json_data.encode('ascii'),
                              headers={'Content-Type': 'application/json'})
    except Exception as em:
        #Fall-back to sending an email
        print(send_error_notification(em))

def send_email(msg):
    try:
        s = smtplib.SMTP("relay.city.phila.local")
        s.set_debuglevel(1)
        s.send_message(msg)
        s.quit()
    except:
        print("Fail")

@click.command()
@click.option('--save-s3', is_flag=True, default=False, help='Save site to S3 bucket.')
@click.option('--s3-bucket', default='static.merge.phila.gov', help='When saving to S3, the bucket to use.')
@click.option('--logging-config', default='logging_config.conf')
def main(save_s3, s3_bucket, logging_config):
    logger = init_logger(logging_config)
    s3_client = boto3.resource('s3')
    s3_bucket = s3_client.Bucket('static.merge.phila.gov')

    logger.info('Starting scraper')

    error = config["error"]
    start_time = datetime.datetime.now()
    try:
        # Only proceed if the last run was successful
        # Forces an admin to manually clear the flag
        # Hopefully after fixing whatever it is went wrong
        if error == False:
            api_query_url = API_URL + "?timestamp=" + LASTRUN
            logger.info('Fetching page list from: {}'.format(api_query_url))
            static_pages = open('staticfiles.csv','r').read().splitlines()
            for page in static_pages:
                logger.info('Saving static file {}'.format(page))
                save_page(page, save_s3, s3_client, s3_bucket)

            page_data = get_pages_list(api_query_url)
            for page in page_data:
                url = page["link"]
                logger.info('Scraping: {}'.format(url))
                save_page(url, save_s3, s3_client, s3_bucket)

            # finally set the LastRun value and save to the config file
            config["LastRun"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            print("Error!")
            #post_to_slack("There was an error scraping beta.phila.gov on the last run. Please clear the error.")
    except:
        error = True
        logger.exception('Exception occured scraping site')
        #post_to_slack("Error scraping beta.phila.gov")
    finally:
        config["error"] = error
        #with open('config.json', 'w') as outfile:
        #    json.dump(config, outfile)

if __name__ == '__main__':
    main()
