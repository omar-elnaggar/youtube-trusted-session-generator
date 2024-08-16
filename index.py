import asyncio
import json
import os
import sys
from kubernetes import client, config
from nodriver import start, cdp, loop


async def main():
    browser = await start(headless=False)
    print("[INFO] launching browser.")
    tab = browser.main_tab
    tab.add_handler(cdp.network.RequestWillBeSent, send_handler)
    page = await browser.get('https://www.youtube.com/embed/jNQXAC9IVRw')
    await tab.wait(cdp.network.RequestWillBeSent)
    button_play = await tab.select("#movie_player")
    await button_play.click()
    await tab.wait(cdp.network.RequestWillBeSent)
    print("[INFO] waiting additional 30 seconds for slower connections.")
    await tab.sleep(30)


async def send_handler(event: cdp.network.RequestWillBeSent):
    if "/youtubei/v1/player" in event.request.url:
        post_data = event.request.post_data
        post_data_json = json.loads(post_data)
        visitor_data = post_data_json["context"]["client"]["visitorData"]
        po_token = post_data_json["serviceIntegrityDimensions"]["poToken"]
        print(f"[INFO] Extracted visitor_data: {visitor_data}")
        print(f"[INFO] Extracted po_token: {po_token}")
        await update_k8s_secret(visitor_data, po_token)
        sys.exit(0)


async def update_k8s_secret(visitor_data, po_token):
    # Load Kubernetes configuration for in-cluster execution
    config.load_incluster_config()

    # Define the Kubernetes API client
    api_instance = client.CoreV1Api()

    # Read the secret name from environment variable
    secret_name = os.getenv("SECRET_NAME", "default-secret-name")

    # Fetch the existing secret
    try:
        secret = api_instance.read_namespaced_secret(
            name=secret_name, namespace="default")
        config_data = secret.data.get("INVIDIOUS_CONFIG", "").decode("utf-8")

        # Replace placeholders with actual values
        updated_config_data = config_data.replace(
            "{{VISITOR_DATA}}", visitor_data).replace("{{PO_TOKEN}}", po_token)

        # Update the secret with new data
        secret.data = {
            "INVIDIOUS_CONFIG": updated_config_data.encode("utf-8")
        }
        api_instance.replace_namespaced_secret(
            name=secret_name, namespace="default", body=secret)
        print(f"[INFO] Secret '{secret_name}' updated successfully.")

    except client.exceptions.ApiException as e:
        print(f"[ERROR] An error occurred while updating the secret: {e}")

if __name__ == '__main__':
    loop().run_until_complete(main())
