import requests

def test_dashboard():
    login_url = "http://localhost:8080/api/v1/auth/login"
    login_data = {
        "email": "buyer@mysuf.com",
        "password": "Password123",
        "client_type": "BUYER_ANDROID"
    }
    print("Logging in...")
    resp = requests.post(login_url, json=login_data)
    print("Login status:", resp.status_code)
    if resp.status_code != 200:
        print("Login failed:", resp.text)
        return
    token = resp.json().get("access_token")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    home_url = "http://localhost:8080/api/v1/users/me/home"
    print("Fetching home...")
    resp = requests.get(home_url, headers=headers)
    print("Home status:", resp.status_code)
    print("Home response:", resp.text)

if __name__ == "__main__":
    test_dashboard()
