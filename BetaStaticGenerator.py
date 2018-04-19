# Import the modules
import os
import requests
import json
import datetime

# Get our Config Values
config = json.load(open('config.json'))
BETA_URL = config["BetaUrl"]
PERPAGE_URL = config["PerPageUrl"]
PERPAGEAND_URL = config["PerPageAndUrl"]
SAVE_FOLDER = config["SaveFolder"]
NEW_URL = config["NewUrl"]
HEADER = {'user-agent': 'beta-static-generator/0.0.1'}
LASTRUN = datetime.datetime.strptime(config["LastRun"], "%Y-%m-%d %H:%M:%S")

# Class that holds information about the service
# Not much hear yet, but wanted to put it in a class
# for future expansion. We may just replace with a list of 
# urls
class ServiceEndPoint:
    def __init__(self, url):
        self.url = url
    count = 0

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

# Gets the total number of posts for the current type
def GetPageCount(url):
    count = 0

    response = requests.get(BETA_URL + url + PERPAGE_URL, headers = HEADER)
    count = response.headers["x-wp-totalpages"]

    return count

# Gets the basic metadata for the item, used to get URL and modified date/time
def ProcessPage(url, x):
    response = requests.get(BETA_URL + url + "/?page=" + str(x) + PERPAGEAND_URL, headers = HEADER)
    data = response.json()
    for pageData in data:
        pageAddress = pageData["link"]
        # Call function to save the page now that we have our link
        SavePage(pageAddress)    

# Start of application. 
error = config["Error"]
startTime = datetime.datetime.now()
try:
    # Only proceed if the last run was successful
    # Forces an admin to manually clear the flag
    # Hopefully after fixing whatever it is went wrong
    if error == "False":
        endpoints = list()
        endpoints.append(ServiceEndPoint("bada"))
        #endpoints.append(ServiceEndPoint("posts"))

        # process each endpoint in our list
        for service in endpoints:
            service.count = GetPageCount(service.url)
            for x in range(1, int(service.count)):
                ProcessPage(service.url, x)

        # finally set the LastRun value and save to the config file
        config["LastRun"] = startTime.strftime("%Y-%m-%d %H:%M:%S")
except:
    error = "True"
finally:
    config["Error"] = error
    with open('config.json', 'w') as outfile:
        json.dump(config, outfile)