import discogs_client
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy
import paho.mqtt.client as mqtt
import re
import sys
import soco
from soco.plugins.sharelink import ShareLinkPlugin
device = soco.discover().pop()

# Replace these with your actual Discogs and Spotify credentials
DISCOGS_TOKEN = 'XXX'
SPOTIFY_CLIENT_ID = 'XXX'
SPOTIFY_CLIENT_SECRET = 'XXX'

# MQTT Broker details
MQTT_BROKER = 'localhost'  # Replace with your broker's address
MQTT_PORT = 1883
MQTT_TOPIC = "X"
MQTT_USERNAME = 'mqtt'  # Replace with your MQTT username
MQTT_PASSWORD = 'mqtt'  # Replace with your MQTT password

d = discogs_client.Client('MyDiscogsApp/1.0', user_token=DISCOGS_TOKEN)

def on_message(client, userdata, msg):
    print(f"Received message: {msg.payload.decode()} on topic: {msg.topic}")
    sanitized_string = re.sub(r'[^0-9]', '', msg.payload.decode())
    find_album_on_spotify(sanitized_string)

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_disconnect(client, userdata, rc):
    print(f"Disconnected with result code {rc}")
    connect_with_retry()

client = mqtt.Client()
client.on_message = on_message
client.on_connect = on_connect
client.on_disconnect = on_disconnect

# Connect to the broker
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD) 

def connect_with_retry():
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            print(f"Connection failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)

def clean_album_title(album_title, artist):
    """Remove artist name from the beginning of the album title if it appears there followed by ' - '."""
    if album_title.startswith(f"{artist} - "):
        album_title = album_title[len(artist) + 3:]  # Remove artist name and " - "
    return album_title

def get_album_from_discogs(upc_code):
    """Search for album information using Discogs API client based on a UPC code."""
    results = d.search(barcode=upc_code, type='release')
    
    # Check if any results were found
    if results:
        release = results[0]  # Get the first result
        album_title = release.title
        artist = release.artists[0].name if release.artists else "Unknown Artist"
        print(f"Found Album: {album_title} by {artist}")
        
        # Clean the album title
        album_title = clean_album_title(album_title, artist)
        
        # Clean the artist
        pattern = r" \(\d+\)$"
        artist = re.sub(pattern, "", artist).strip()
        return album_title, artist
        
    else:
        print("No album found for this UPC.")
        return None, None

def search_album_on_spotify(album_title, artist):
    """Search for an album on Spotify given the album title and artist, printing all results."""
    # Spotify Authentication
    auth_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
    sp = spotipy.Spotify(auth_manager=auth_manager)

    # Search for the album on Spotify
    query = f"album:{album_title} artist:{artist}"
    results = sp.search(q=query, type='album', limit=10)  # Increase limit if you want more results
    # Check if any results were found
    if results['albums']['items']:
        album = results['albums']['items'][0]
        album_name = album['name']
        spotify_url = album['external_urls']['spotify']
        print(f"Spotify Album Found: {album_name} - {spotify_url}")
        return spotify_url
    else:
        print("Album not found on Spotify.")
        return None

def find_album_on_spotify(upc_code):
    album_title, artist = get_album_from_discogs(upc_code)
    if album_title and artist:
        search_results = search_album_on_spotify(album_title, artist)
        if search_results:
            device.clear_queue() 
            share_link = ShareLinkPlugin(device)
            share_link.add_share_link_to_queue(search_results)
            device.play_from_queue(index=0)
            print("Sent to player", search_results)
    else:
        print("Album identification failed.")

if len(sys.argv) > 1:
    barcode = sys.argv[1]  # The first argument is the temperature
    print(f"Received barcode: {barcode}")
    sanitized_string = re.sub(r'[^0-9]', '', barcode)
    find_album_on_spotify(sanitized_string)
else:
    connect_with_retry()
    client.subscribe(MQTT_TOPIC)
    print(f"Listening for messages on topic: {MQTT_TOPIC}...")
    client.loop_forever()



