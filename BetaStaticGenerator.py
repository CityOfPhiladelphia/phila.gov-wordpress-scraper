import requests, os

BETA_URL = "https://beta.phila.gov/wp-json/wp/v2/"
PERPAGE_URL = "?per_page=1"
PERPAGEAND_URL = "&per_page=1"
SAVE_FOLDER = "c:/beta/"
NEW_URL = "market.phila.gov"

class ServiceEndPoint:
    def __init__(self, url):
        self.url = url
    count = 0

def SavePage(url):
    headers = {'user-agent': 'beta-static-generator/0.0.1'}
    response = requests.get(url, headers = headers)
    folderPath = SAVE_FOLDER + url.replace("https://beta.phila.gov/", "")
    if not os.path.exists(folderPath):
        print('Creating folder ' + folderPath)
        os.makedirs(folderPath)
    f = open(folderPath + 'index.html','w', encoding="utf-8")
    f.write(response.text)
    f.close()

def GetPageCount(url):
    count = 0

    headers = {'user-agent': 'beta-static-generator/0.0.1'}
    response = requests.get(BETA_URL + url + PERPAGE_URL, headers = headers)
    count = response.headers["x-wp-totalpages"]

    return count

def ProcessPage(url, x):
    headers = {'user-agent': 'beta-static-generator/0.0.1'}
    response = requests.get(BETA_URL + url + "/?page=" + str(x) + PERPAGEAND_URL, headers = headers)
    data = response.json()
    for pageData in data:
        pageAddress = pageData["link"]
        SavePage(pageAddress)    

endpoints = list()
endpoints.append(ServiceEndPoint("posts"))

for service in endpoints:
    service.count = GetPageCount(service.url)
    for x in range(1, int(service.count)):
        ProcessPage(service.url, x)

