import os
import requests
import json
import datetime
import smtplib
from email.mime.text import MIMEText
import boto3
import botocore
import json

# Set our Config Values
SAVE_FOLDER = "sitefiles/"
HEADER = {'user-agent': 'beta-static-generator/0.0.1'}
API_URL = "https://beta.phila.gov/wp-json/last-updated/v1/all"
BUCKET = "static.merge.phila.gov"
MAIL_SERVER = "relay.city.phila.local"
OLD_WEB_URL = "https://beta.phila.gov/"

def get_pages_list(url):
    response = requests.get(url, headers = HEADER)
    print(response)
    data = response.json()
    return data

def send_error_notification(e):
    try:
        subject = "Merger tool encountered errors when deleting unused or deleted pages/resources."
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
        s = smtplib.SMTP(MAIL_SERVER)
        s.set_debuglevel(1)
        s.send_message(msg)
        s.quit()
    except:
        print("Fail")

def check_for_delete(_current_key):
    if _current_key.replace(SAVE_FOLDER, "") in urls:
        print("Found a match for " + _current_key)
    else:
        if not any(map(_current_key.replace(SAVE_FOLDER, "").startswith, old_sites_array)):
            print("Kill it with fire!!! " + _current_key)
            s3.delete_object(Bucket=BUCKET, Key=_current_key)
        else:
            print("Found an old phila.gov file")

try:
    # get list of sharepoint sites  
    old_sites_array = open('oldphilagov.csv','r').read().splitlines()
    
    # process each endpoint in our list
    pageData = get_pages_list(API_URL)
    urls = list()
    for page in pageData:
        #We're auto-generating files, so check for index.html
        urls.append(page["link"].replace(OLD_WEB_URL, ""))
        if (page["link"].endswith("/")):
            urls.append(page["link"].replace(OLD_WEB_URL, "") + "index.html")       
    
    s3FileKeys = list()
    s3FolderKeys = list()
    s3 = boto3.client('s3')

    resp = s3.list_objects(Bucket=BUCKET, Prefix=SAVE_FOLDER, Delimiter='/')
    for obj in resp['CommonPrefixes']:
        s3FolderKeys.append(str(obj['Prefix']))

    resp = s3.list_objects(Bucket=BUCKET, Prefix=SAVE_FOLDER)
    for obj in resp['Contents']:
        if not obj['Key'] in s3FolderKeys:
            s3FileKeys.append(str(obj['Key']))

    for currentKey in s3FileKeys:
        check_for_delete(currentKey)
    
    for currentFolder in s3FolderKeys:
        check_for_delete(currentFolder)


except BaseException as e:
    error = "True"
    #PostToSlack("Error scraping beta.phila.gov" + str(e))
