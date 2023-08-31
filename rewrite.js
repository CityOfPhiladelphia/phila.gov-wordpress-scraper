// This code scrapes a website and saves the pages to a file.

const fs = require('fs'); // The fs module is used to read and write files.
const https = require('https'); // The https module is used to make HTTP requests.
const yaml = require('js-yaml'); // The yaml module is used to load YAML configuration files.
const uuid = require('uuid'); // The uuid module is used to generate random UUIDs.
const moment = require('moment'); // The moment module is used to work with dates and times.
const queue = import('queue'); // The queue module is used to manage a queue of tasks.
const threading = require('threading'); // The threading module is used to create and manage threads.

// The `logger` function is used to print messages to the console.
const logger = console.log;

// The `runId` variable is a unique identifier for this run of the scraper.
const runId = uuid.v4();

// The `config` variable is the configuration for the scraper. It is loaded from a YAML file.
// const config = yaml.load(fs.readFileSync('logging_config.conf'));

// This function is used to scrape a page and save it to a file.
async function scrapePage(url) {
  // Make an HTTP request to the page.
  const response = await https.get(url);

  // Get the content type of the response.
  const contentType = response.headers['content-type'];

  // Get the content of the response.
  const content = await response.text();

  // // If the content type is text/html, then replace all occurrences of the `r` regular expression with the `e` string.
  // if (contentType === 'text/html') {
  //   content = content.replace(r, e);
  // }

  // Save the content to a file.
  fs.writeFileSync(`sitefiles/${url}`, content);
}

async function getPages(url) {
  return await https.get(url);
}

// This function is used to start the scraper.
async function startScraper() {
  // Create a queue to store the pages to be scraped.
  const queue = [];

  // Create a list of threads to scrape the pages.
  const threads = [];

  // Add the static files to the queue.
  const staticFiles = fs.readFileSync('staticfiles.csv').toString().split('\n');
  staticFiles.forEach(url => queue.push([3, url, undefined]));

  // Get the list of pages from the database.
  const pages = await getPages('https://test-admin.phila.gov/wp-json/last-updated/v1/all');
  console.log(pages)

  // Add the pages from the database to the queue.
  pages.forEach(page => queue.push([2, page.url, page.updatedAt]));

  // Start the threads.
  for (let i = 0; i < 6; i++) {
    const thread = new threading.Thread(() => {
      while (true) {
        // Get the next task from the queue.
        const [type, url, updatedAt] = queue.pop();

        // If the task is a signal to stop, then break.
        if (type === 1) {
          break;
        }

        // Scrape the page.
        scrapePage(url);
      }
    });

    threads.push(thread);
    thread.start();
  }

  // Wait for all the threads to finish.
  for (const thread of threads) {
    thread.join();
  }

  // Print the stats.
  logger.info('Stats - Pages Scraped: {}, Pages New: {}, Pages Updated: {}', pagesScraped, pagesNew, pagesUpdated);
}

// This is the main function. It starts the scraper.
startScraper();
