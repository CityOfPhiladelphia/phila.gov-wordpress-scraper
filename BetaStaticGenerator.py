# Import the modules
import os
import requests

# Declare some constants
BETA_URL = "https://beta.phila.gov/wp-json/wp/v2/"
PERPAGE_URL = "?per_page=1"
PERPAGEAND_URL = "&per_page=1"
SAVE_FOLDER = "sitefiles/"
NEW_URL = "market.phila.gov"
HEADER = {'user-agent': 'beta-static-generator/0.0.1'}

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

# Start of application. Build out list of end-points
endpoints = list()
endpoints.append(ServiceEndPoint("pages"))
endpoints.append(ServiceEndPoint("posts"))

# process each endpoint in our list
for service in endpoints:
    service.count = GetPageCount(service.url)
    for x in range(1, int(service.count)):
        ProcessPage(service.url, x)