import threading
from functools import wraps
from threading import Thread

import allure
import nose
import yaml
import logging
import logging.config
from selenium import webdriver
from selenium.webdriver import Proxy, DesiredCapabilities
from selenium.webdriver.common.by import By
from io import BytesIO
from PIL import Image
from selenium.webdriver.common.proxy import ProxyType

with open("config.yaml", 'r') as stream:
    config = yaml.load(stream)

logging.config.fileConfig('logging.conf')

# create logger
logger = logging.getLogger('simpleExample')

def debug(message):
    logging.debug(msg=message)
    nose.allure.attach('', message)


class Links():

    def __init__(self, url, parent_url):
        self.url = url
        self.parent_url = parent_url

    def navigate(self):
        pass

    # allows '==' operator
    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.url == other.url
        elif type(other) == str:
            return self.url == other
        else:
            return False


    def __contains__(self, item):
        if self.url.contains(item):
            return True
        else:
            return False

    def contains(self, item):
        if type(item) == list:
            b = False
            for _ in item:
                if _ in self.url:
                    b = True
            return b
        elif type(item) == str:
            if item in self.url:
                return True
            else:
                return False

    def startswith(self, item):
        if type(item) == list:
            b = False
            for _ in item:
                if self.url.startswith(_):
                    b = True
            return b
        elif type(item) == str:
            if self.url.startswith(item):
                return True
            else:
                return False

    def split(self, item):
        if type(item) == str:
            self.url = self.url.split(item)[0]


class SiteCrawler():

    def __init__(self, driver):
        self.driver = driver
        self.to_navigate_queue = []
        self.to_navigate_queue.append(Links(config['base_url'], 'init'))
        self.visited_links = []
        self.add_new_links_to_navigate()

    def get_page_links(self):
        links = self.driver.find_elements_by_tag_name("a")
        current_url = self.driver.current_url
        all_links = []
        for _ in links:
            if _.get_attribute("href") is not None:
                all_links.append(Links(_.get_attribute("href"), current_url))
        logging.debug("Found {} links".format(str(len(all_links))))
        return all_links

    def print_queue(self):
        s = str(len(self.to_navigate_queue))
        for _ in self.to_navigate_queue:
            s += _.url.strip(config["base_url"])+" "
        return s

    def get_new_links(self, new_list, comparision_list):
        to_remove = []
        for new_link in new_list:
            for old_link in comparision_list:
                if new_link == old_link:
                    logging.info("Removing {} from the new list".format(new_link.url))
                    to_remove.append(new_link)
                else:
                    logging.debug("{} is not {}".format(str(new_link.url), str(old_link.url)))
        for _ in to_remove:
            new_list.remove(_)
        return new_list

    def add_new_links_to_navigate(self):
        new_links = self.get_page_links()

        logging.debug("Removing outside sites")
        new_links = self.remove_outside_links(new_links)
        logging.debug("Removing URL Parameters")
        new_links = self.remove_url_parameters(new_links)

        logging.debug("Removing duplicates")
        new_links = self.remove_duplicates(new_links)
        # make sure links are not in the queue
        logging.debug("Comparing to queue")
        new_links = self.get_new_links(new_links, self.to_navigate_queue)
        # make sure links have not been visted
        logging.debug("Comparing to Visited Links")
        new_links = self.get_new_links(new_links, self.visited_links)
        logging.debug("Comparing to No Fly List")
        new_links = self.remove_do_not_navigate(new_links)

        for _ in new_links:
            if _.url is not None:
                self.to_navigate_queue.append(_)

    @nose.allure.step('Removing URL parameters')
    def remove_url_parameters(self, links):
        for link in links:
            # add in patterns for pagination or whatever has duplicate pages in system into config file
            for pattern in config["pattern"]:
                if link.contains(pattern):
                    logging.debug("Splitting {} on {}".format(link.url, pattern))
                    link = link.split(pattern)
        return links

    @nose.allure.step('Removing non-essential links to crawl')
    def remove_do_not_navigate(self, links):
        for link in links:
            # add in patterns for pagination or whatever has duplicate pages in system into config file
            for pattern in config["do_not_navigate"]:
                if link.contains(pattern):
                    logging.debug("Removing {} from list".format(link.url))
                    links.remove(link)
        return links

    @nose.allure.step('Removing in list')
    def remove_duplicates(self, list):
        for l in list:
            count = 0
            for x in list:
                if l == x:
                    count += 1
            if count > 1:
                logging.debug("Found {} occurrences of {}".format(str(count), l.url))
                list.remove(l)
        return list

    @nose.allure.step('Removing outside links')
    def remove_outside_links(self, links):
        remove = []
        for link in links:
            if not link.contains(config["base_url"]):
                logging.debug("The link {} is outside of the base site".format(link.url))
                link.old = link.url
                link.url = None
                remove.append(link)
        for r in remove:
            links.remove(r)
        return links

    @nose.allure.step('Shuffling URLs that need to be scanned last to the bottom')
    def navigate_to_next(self):
        if self.to_navigate_queue[0].contains(config["logout"]):
            if self.to_navigate_queue > 1:
                self.to_navigate_queue.append(self.to_navigate_queue[0])
                self.to_navigate_queue.pop(0)
        if not self.to_navigate_queue[0].startswith(config["base_url"]):
            self.to_navigate_queue.pop(0)
        return self.to_navigate_queue[0]

    @nose.allure.step('Navigating to next URL')
    def navigate(self):
        link = self.navigate_to_next()
        self.driver.get(link.url)
        self.visited_links.append(link)
        self.to_navigate_queue.pop(0)


    def clean_url_for_file(self, url):
        return url.replace('/', '-')

    @nose.allure.step('Screenshot of Page')
    def save_screenshot(self, url):
        verbose = 0

        # hide fixed header
        # js_hide_header=' var x = document.getElementsByClassName("topnavbar-wrapper ng-scope")[0];x[\'style\'] = \'display:none\';'
        # self.driver.execute_script(js_hide_header)

        # get total height of page
        js = 'return Math.max( document.body.scrollHeight, document.body.offsetHeight,  document.documentElement.clientHeight,  document.documentElement.scrollHeight,  document.documentElement.offsetHeight);'

        scrollheight = self.driver.execute_script(js)
        if verbose > 0:
            print(scrollheight)

        slices = []
        offset = 0
        offset_arr = []

        # separate full screen in parts and make printscreens
        while offset < scrollheight:
            if verbose > 0:
                print(offset)

            # scroll to size of page
            if (scrollheight - offset) < offset:
                # if part of screen is the last one, we need to scroll just on rest of page
                self.driver.execute_script("window.scrollTo(0, %s);" % (scrollheight - offset))
                offset_arr.append(scrollheight - offset)
            else:
                self.driver.execute_script("window.scrollTo(0, %s);" % offset)
                offset_arr.append(offset)

            # create image (in Python 3.6 use BytesIO)
            img = Image.open(BytesIO(self.driver.get_screenshot_as_png()))

            offset += img.size[1]
            # append new printscreen to array
            slices.append(img)

            if verbose > 0:
                self.driver.get_screenshot_as_file('screen_%s.jpg' % (offset))
                print(scrollheight)

        # create image with
        screenshot = Image.new('RGB', (slices[0].size[0], scrollheight))
        offset = 0
        offset2 = 0
        # now glue all images together
        for img in slices:
            screenshot.paste(img, (0, offset_arr[offset2]))
            offset += img.size[1]
            offset2 += 1
        file = '{}.png'.format(url)
        screenshot.save(file)
        nose.allure.attach(file, 'Screenshot of {}'.format(url))

    def crawl(self):
        while len(self.to_navigate_queue) > 0:
            if self.navigate_to_next().contains(config["login"]):
                self.login()
            elif self.navigate_to_next().contains(config["logout"]):
                self.logout()
            else:
                self.navigate()
                self.per_page()
                self.add_new_links_to_navigate()

    # Modify this method if you need to login to your own system
    def login(self):
        pass


    # If you need to run any special code on specific pages you can do that here
    # EG hover over dropdown menus
    def per_page(self):
        pass

    # Any special commands that you want to run to logout
    def logout(self):
        pass

@nose.allure.feature('Not Vunerable')
@nose.allure.story('All Pages')
def crawl_test():
    PROXY = "localhost:8090"  # IP:PORT or HOST:PORT

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument('--proxy-server=%s'.format(PROXY))
    driver = webdriver.Chrome(chrome_options=chrome_options)

    SC = SiteCrawler(driver)
    SC.crawl()

if __name__ == '__main__':
    crawl_test()