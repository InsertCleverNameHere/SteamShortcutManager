from steam.client import SteamClient

def test_anonymous_info(appid):
    client = SteamClient()
    print("Connecting to Steam anonymously...")
    client.anonymous_login()
    
    # Attempt to get product info
    # 1 is the 'apps' type
    product_info = client.get_product_info(apps=[appid])
    
    if product_info:
        print("✅ Success! Manifest retrieved.")
        # This is where we would hunt for:
        # product_info['apps'][appid]['common']['library_assets']
        print(product_info['apps'][appid])
    else:
        print("❌ Access Denied. Valve requires a logged-in session for this AppID's manifest.")
    
    client.disconnect()

if __name__ == "__main__":
    test_anonymous_info(3489700) # Vector