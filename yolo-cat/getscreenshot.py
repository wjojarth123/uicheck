import os
import time
import asyncio
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse
import logging
from PIL import Image
import threading

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_driver():
    """Set up Chrome WebDriver with optimal settings for screenshots"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in background
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")  # Set window size for high resolution capture
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")  # Only fatal errors
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--disable-iframes-during-prerender")
    
    # Disable images and CSS for faster loading (optional)
    # chrome_options.add_argument("--disable-images")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)
    return driver

def sanitize_filename(url):
    """Convert URL to safe filename"""
    # Remove protocol and www
    domain = url.replace('https://', '').replace('http://', '').replace('www.', '')
    # Replace invalid characters
    safe_chars = '-_.'
    sanitized = ''.join(c if c.isalnum() or c in safe_chars else '_' for c in domain)
    return sanitized

def take_screenshot(driver, url, output_dir, thread_id):
    """Take a screenshot at 1920x1080 and downscale to 1139x640 for saving"""
    try:
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            full_url = f'https://{url}'
        else:
            full_url = url
            
        logging.info(f"Thread {thread_id} - Capturing screenshot of: {full_url}")
        
        # Navigate to the website
        driver.get(full_url)
        
        # Wait for page to load
        WebDriverWait(driver, 15).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
        
        # Additional wait for dynamic content
        time.sleep(3)
        
        # Set window size for high resolution capture
        driver.set_window_size(1920, 1080)
        time.sleep(1)
        
        # Generate temporary filename for full resolution
        temp_filename = f"temp_{thread_id}_{sanitize_filename(url)}.png"
        temp_filepath = os.path.join(output_dir, temp_filename)
        
        # Take high resolution screenshot
        driver.save_screenshot(temp_filepath)
        
        # Open and resize the image using PIL
        with Image.open(temp_filepath) as img:
            # Calculate new dimensions maintaining 16:9 ratio with 640 on short edge
            original_width, original_height = img.size
            
            # For 16:9 ratio with 640 height: width = 640 * (16/9) = 1138.67 ≈ 1139
            new_width = 1139
            new_height = 640
            
            # Resize with high quality resampling
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Generate final filename
            filename = f"{sanitize_filename(url)}.png"
            filepath = os.path.join(output_dir, filename)
            
            # Save resized image
            resized_img.save(filepath, "PNG", optimize=True)
        
        # Remove temporary file
        os.remove(temp_filepath)
        
        logging.info(f"Thread {thread_id} - Screenshot saved (1920x1080 → 1139x640): {filepath}")
        return True
        
    except Exception as e:
        logging.error(f"Thread {thread_id} - Error capturing {url}: {str(e)}")
        return False

def worker_thread(url_batch, output_dir, thread_id, results):
    """Worker function for each thread"""
    driver = None
    successful = 0
    failed = 0
    
    try:
        driver = setup_driver()
        
        for url in url_batch:
            if take_screenshot(driver, url, output_dir, thread_id):
                successful += 1
            else:
                failed += 1
                
            # Small delay between requests to be respectful
            time.sleep(1)
            
    except Exception as e:
        logging.error(f"Thread {thread_id} - Critical error: {str(e)}")
        
    finally:
        if driver:
            driver.quit()
            
    results[thread_id] = {'successful': successful, 'failed': failed}
    logging.info(f"Thread {thread_id} completed - Success: {successful}, Failed: {failed}")

def main():
    """Main function to screenshot all websites using 3 concurrent threads
    "https://www.apple.com",
        "https://www.airbnb.com",
        "https://www.spotify.com",
        "https://www.figma.com",
        "https://www.linear.app",
        "https://www.stripe.com",
        "https://www.notion.so",
        "https://www.spline.design",
        "https://www.vercel.com",
        "https://www.duolingo.com",
        "https://www.intercom.com",
        "https://www.dropbox.com",
        "https://www.slack.com",
        "https://www.adobe.com",
        "https://www.medium.com",
        "https://www.heroku.com",
        "https://www.github.com",
        "https://www.netlify.com",
        "https://www.carrd.co",
        "https://www.webflow.com",
        "https://www.shopify.com",
        "https://www.pitch.com",
        "https://www.canva.com",
        "https://www.abstract.com",
        "https://www.invisionapp.com",
        "https://www.uber.com",
        "https://www.lyft.com",
        "https://www.doordash.com",
        "https://www.robinhood.com",
        "https://www.coinbase.com",
        "https://www.brex.com",
        "https://www.replit.com",
        "https://www.raycast.com",
        "https://www.superhuman.com",
        "https://www.grammarly.com",
        "https://www.niice.co",
        "https://www.awwwards.com",
        "https://www.behance.net",
        "https://www.dribbble.com",
        "https://www.producthunt.com",
        "https://www.framer.com",
        "https://www.loom.com",
        "https://www.twitch.tv",
        "https://www.discord.com",
        "https://www.figma.com",
        "https://www.sketch.com",
        "https://www.principleformac.com",
        "https://www.protopie.io",
        "https://www.whimsical.com",
        "https://www.miro.com",
        "https://www.notion.so",
        "https://www.trello.com",
        "https://www.asana.com",
        "https://www.clickup.com",
        "https://www.monday.com",
        "https://www.basecamp.com",
        "https://www.slack.com",
        "https://www.microsoft.com",
        "https://www.google.com",
        "https://www.meta.com",
        "https://www.twitter.com",
        "https://www.instagram.com",
        "https://www.tiktok.com",
        "https://www.snapchat.com",
        "https://www.pinterest.com",
        "https://www.linkedin.com",
        "https://www.reddit.com",
        "https://www.quora.com",
        "https://www.youtube.com",
        "https://www.vimeo.com",
        "https://www.netflix.com",
        "https://www.hulu.com",
        "https://www.disneyplus.com",
        "https://www.primevideo.com",
        "https://www.hbo.com",
        "https://www.crunchyroll.com",
        "https://www.twitch.tv",
        "https://www.soundcloud.com",
        "https://www.bandcamp.com",
        "https://www.pandora.com",
        "https://www.tidal.com",
        "https://www.deezer.com",
        "https://www.shazam.com",
        "https://www.shutterstock.com",
        "https://www.unsplash.com",
        "https://www.pexels.com",
        "https://www.gettyimages.com",
        "https://www.adobe.com",
        "https://www.blender.org",
        "https://www.unrealengine.com",
        "https://www.autodesk.com",
        "https://www.zbrush.com",
        "https://www.procreate.art",
        "https://www.figma.com",
        "https://www.sketch.com",
        "https://www.invisionapp.com",
        "https://www.etsy.com",
        "https://www.ebay.com",
        "https://www.cnn.com",
        "https://www.bbc.com",
        "https://www.wikipedia.org",
        "https://www.reddit.com",
        "https://www.imdb.com",
        "https://www.craigslist.org",
        "https://www.nytimes.com",
        "https://www.walmart.com",
        "https://www.target.com",
        "https://www.yelp.com",
        "https://www.quora.com",
        "https://www.forbes.com",
        "https://www.huffpost.com",
        "https://www.businessinsider.com",
        "https://www.theguardian.com",
        "https://www.washingtonpost.com",
        "https://www.usatoday.com",
        "https://www.bloomberg.com",
        "https://www.reuters.com",
        "https://www.aljazeera.com",
        "https://www.foxnews.com",
        "https://www.cbsnews.com",
        "https://www.nbcnews.com",
        "https://www.msnbc.com",
        "https://www.espn.com",
        "https://www.nfl.com",
        "https://www.nba.com",
        "https://www.mlb.com",
        "https://www.fifa.com",
        "https://www.ign.com",
        "https://www.gamespot.com",
        "https://www.polygon.com",
        "https://www.kotaku.com",
        "https://www.techcrunch.com",
        "https://www.theverge.com",
        "https://www.wired.com",
        "https://www.gizmodo.com",
        "https://www.engadget.com",
        "https://www.cnet.com",
        "https://www.pcmag.com",
        "https://www.zdnet.com",
        "https://www.tomsguide.com",
        "https://www.androidauthority.com",
        "https://www.macrumors.com",
        "https://www.9to5mac.com",
        "https://www.thehill.com",
        "https://www.politico.com",
        "https://www.axios.com",
        "https://www.vox.com",
        "https://www.buzzfeed.com",
        "https://www.mashable.com",
        "https://www.gizmodo.com",
        "https://www.lifehacker.com",
        "https://www.deadspin.com",
        "https://www.jalopnik.com",
        "https://www.kotaku.com",
        "https://www.jezebel.com",
        "https://www.theonion.com",
        "https://www.clickhole.com",
        "https://www.cracked.com",
        "https://www.collegehumor.com",
        "https://www.funnyordie.com",
        "https://www.thechive.com",
        "https://www.cheezburger.com",
        "https://www.boredpanda.com",
        "https://www.imgur.com",
        "https://www.deviantart.com",
        "https://www.artstation.com",
        "https://www.500px.com",
        "https://www.flickr.com",
        "https://www.smugmug.com",
        "https://www.photobucket.com",
        "https://www.picsart.com",
        "https://www.vsco.co",
        "https://www.eyeem.com",
        "https://www.1x.com",
        "https://www.viewbug.com",
        "https://www.youpic.com",
        "https://www.alamy.com",
        "https://www.dreamstime.com",
        "https://www.istockphoto.com",
        "https://www.bigstockphoto.com",
        "https://www.depositphotos.com",
        "https://www.fotolia.com",
        "https://www.canstockphoto.com",
        "https://www.123rf.com",
        "https://www.pond5.com",
        "https://www.storyblocks.com",
        "https://www.videoblocks.com",
        "https://www.audioblocks.com",
        "https://www.motionarray.com",
        "https://www.videohive.net",
        "http://www.arngren.net",
        "http://www.spacejam.com/1996",
        "http://www.lingscars.com",
        "http://www.pennyjuice.com",
        "http://www.art.yale.edu",
        "http://www.berkshirehathaway.com",
        "http://www.mmspa.com",
        "http://www.sacred-texts.com",
        "http://www.ratemypoo.com",
        "http://www.timecube.com",
        "http://www.dokimos.org/ajff",
        "http://www.paulgraham.com",
        "http://www.theworstwebsiteever.com",
        "http://www.mrbottles.com",
        "http://www.dihard.com",
        "http://www.bigblackbooty.com",
        "http://www.ihasabucket.com",
        "http://www.zombo.com",
        "http://www.pointerpointer.com",
        "http://www.staggeringbeauty.com",
        "http://www.koalastothemax.com",
        "http://www.homestarrunner.com",
        "http://www.leekspin.com",
        "http://www.ooooiiii.com",
        "http://www.cameronsworld.net",
        "http://www.theworstoftheweb.com",
        "http://www.muchoweb.com",
        "http://www.websitesthatsuck.com",
        "http://www.badwebsiteideas.com",
        "http://www.uglywebsite.com",
        "http://www.angelfire.com",
        "http://www.geocities.com",
        "http://www.tripod.com",
        "http://www.freewebs.com",
        "http://www.bravenet.com",
        "http://www.webs.com",
        "http://www.000webhost.com",
        "http://www.freehostia.com",
        "http://www.byethost.com",
        "http://www.awardspace.com",
        "http://www.x10hosting.com",
        "http://www.prohosts.org",
        "http://www.freevirtualservers.com","""
    urls = [
        
        "http://www.fatcow.com",
        "http://www.hostgator.com",
        "http://www.bluehost.com",
        "http://www.godaddy.com",
        "http://www.1and1.com",
        "http://www.hostinger.com",
        "http://www.siteground.com",
        "http://www.dreamhost.com",
        "http://www.walmart.com",
        "http://www.target.com",
        "http://www.bestbuy.com",
        "http://www.costco.com",
        "http://www.kroger.com",
        "http://www.walgreens.com",
        "http://www.cvs.com",
        "http://www.sears.com",
        "http://www.jcpenney.com",
        "http://www.macys.com",
        "http://www.kohls.com",
        "http://www.bedbathandbeyond.com",
        "http://www.lowes.com",
        "http://www.homedepot.com",
        "http://www.ikea.com",
        "http://www.wayfair.com",
        "http://www.overstock.com",
        "http://www.zappos.com",
        "http://www.verizon.com",
        "http://www.att.com",
        "http://www.tmobile.com",
        "http://www.sprint.com"
        
]
    
    # Remove duplicates while preserving order
    unique_urls = list(dict.fromkeys(urls))
    
    # Create output directory
    output_dir = "website_screenshots"
    os.makedirs(output_dir, exist_ok=True)
    
    # Split URLs into 3 batches for concurrent processing
    total_urls = len(unique_urls)
    batch_size = (total_urls + 2) // 3  # Divide into 3 roughly equal batches
    
    url_batches = [
        unique_urls[i:i + batch_size] 
        for i in range(0, total_urls, batch_size)
    ]
    
    # Ensure we have exactly 3 batches (pad if needed)
    while len(url_batches) < 3:
        url_batches.append([])
    
    # Only use non-empty batches
    url_batches = [batch for batch in url_batches if batch]
    
    logging.info(f"Starting to capture {total_urls} websites using {len(url_batches)} concurrent threads...")
    for i, batch in enumerate(url_batches):
        logging.info(f"Thread {i+1} will process {len(batch)} URLs")
    
    # Dictionary to store results from each thread
    results = {}
    
    # Start threads
    threads = []
    for i, batch in enumerate(url_batches):
        thread = threading.Thread(
            target=worker_thread, 
            args=(batch, output_dir, i+1, results)
        )
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Calculate total results
    total_successful = sum(r['successful'] for r in results.values())
    total_failed = sum(r['failed'] for r in results.values())
    
    # Summary
    logging.info(f"All threads completed!")
    logging.info(f"Total successful: {total_successful}")
    logging.info(f"Total failed: {total_failed}")
    logging.info(f"Screenshots saved in: {output_dir}")

if __name__ == "__main__":
    main()