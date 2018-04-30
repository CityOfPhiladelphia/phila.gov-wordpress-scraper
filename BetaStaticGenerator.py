# Import the modules
import os
import requests
import json
import datetime
import smtplib
from email.mime.text import MIMEText

# Set our Config Values
config = json.load(open('/home/ec2-user/environment/betastaticsitegenerator/config.json'))
BETA_URL = config["BetaUrl"]
PERPAGE_URL = config["PerPageUrl"]
PERPAGEAND_URL = config["PerPageAndUrl"]
SAVE_FOLDER = config["SaveFolder"]
NEW_URL = config["NewUrl"]
HEADER = {'user-agent': 'beta-static-generator/0.0.1'}
LASTRUN = datetime.datetime.strptime(config["LastRun"], "%Y-%m-%d %H:%M:%S")
API_URL = config["API"]

# Gets a page and saves the content to disk
def SavePage(url):
    response = requests.get(url, headers = HEADER)
    folder = SAVE_FOLDER + url.replace("https://beta.phila.gov/", "")
    if not os.path.exists(folder):
        print('Creating folder ' + folder)
        os.makedirs(folder)
    f = open(folder + 'index.html','w', encoding="utf-8")
    print('Writing file ' + folder + 'index.html')
    f.write(response.text.replace('beta.phila.gov', NEW_URL))
    f.close()

def GetPagesList(url):
    response = requests.get(url)
    print(response)
    data = response.json()
    return data

def SendErrorNotification(e):
    try:
        subject = "Beta generator encountered an error when building the site"
        body = "Error details: " + str(e)
        msg = MIMEText(subject + body)
        msg['Subject'] = subject
        msg['From'] = 'ithelp@phila.gov'
        msg['To'] = 'andrew.kennel@phila.gov'
        SendEmail(msg)
    except:
        print("Fail")

def PostToSlack(message):
    post = {"text": "{0}".format(message)}
 
    try:
        json_data = json.dumps(post)
        requests.post("https://hooks.slack.com/services/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",
                              data=json_data.encode('ascii'),
                              headers={'Content-Type': 'application/json'})
    except Exception as em:
        #Fall-back to sending an email
        print(SendErrorNotification(em))

def SendEmail(msg):
    try:
        s = smtplib.SMTP("relay.city.phila.local")
        s.set_debuglevel(1)
        s.send_message(msg)
        s.quit()
    except:
        print("Fail")

# Start of application. 
error = config["Error"]
startTime = datetime.datetime.now()
try:
    # Only proceed if the last run was successful
    # Forces an admin to manually clear the flag
    # Hopefully after fixing whatever it is went wrong
    if error == "False":
        endpoints = list()
        print(API_URL)
        #endpoints.append(ServiceEndPoint(API_URL))
        #endpoints.append(ServiceEndPoint("posts"))

        # process each endpoint in our list
        pageData = GetPagesList(API_URL)
        print(pageData)
        for page in pageData:
            print(page["link"])
            SavePage(page["link"])

        # finally set the LastRun value and save to the config file
        config["LastRun"] = startTime.strftime("%Y-%m-%d %H:%M:%S")
    else:
        print("Error!")
        #PostToSlack("There was an error scraping beta.phila.gov on the last run. Please clear the error.")
except BaseException as e:
    error = "True"
    #PostToSlack("Error scraping beta.phila.gov")
finally:
    config["Error"] = error
    #with open('config.json', 'w') as outfile:
    #    json.dump(config, outfile)