import os
import base64
import httpx
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.table import Table

# Load environment variables from a .env file
load_dotenv()

class GenesysCloudClient:
    """
    A client for interacting with the Genesys Cloud API to get user statuses.
    """

    def __init__(self, client_id: str, client_secret: str, region: str):
        """
        Initializes the client.

        Args:
            client_id: The OAuth client ID.
            client_secret: The OAuth client secret.
            region: The Genesys Cloud region (e.g., mypurecloud.com).
        """
        if not all([client_id, client_secret, region]):
            raise ValueError("Client ID, Client Secret, and Region must be provided.")
            
        self.base_api_url = f"https://api.{region}"
        self.auth_url = f"https://login.{region}/oauth/token"
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._client = httpx.Client()

    def _get_auth_token(self) -> str:
        """
        Fetches an OAuth token from Genesys Cloud using Client Credentials Grant.
        Caches the token for subsequent requests.
        """
        if self._token:
            return self._token

        print("Authenticating with Genesys Cloud...")
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("utf-8")

        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}

        try:
            response = self._client.post(self.auth_url, headers=headers, data=data)
            response.raise_for_status()
            self._token = response.json()["access_token"]
            print("Authentication successful.")
            return self._token
        except httpx.HTTPStatusError as e:
            print(f"Error authenticating: {e.response.status_code} - {e.response.text}")
            raise

    def _get_headers(self) -> Dict[str, str]:
        """Constructs the necessary headers for API requests."""
        token = self._get_auth_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_queue_id_by_name(self, queue_name: str) -> Optional[str]:
        """
        Finds a queue's ID by its name.
        """
        print(f"Searching for queue: '{queue_name}'...")
        url = f"{self.base_api_url}/api/v2/routing/queues"
        params = {"name": queue_name}
        
        try:
            response = self._client.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            results = response.json()
            
            if results.get("entities"):
                queue_id = results["entities"][0]["id"]
                print(f"Found queue ID: {queue_id}")
                return queue_id
            else:
                print(f"No queue found with the name '{queue_name}'.")
                return None
        except httpx.HTTPStatusError as e:
            print(f"Error finding queue: {e.response.status_code} - {e.response.text}")
            return None

    def get_users_in_queue(self, queue_id: str) -> List[Dict[str, Any]]:
        """
        Gets a list of users associated with a specific queue ID.
        """
        print(f"Fetching users for queue ID: {queue_id}...")
        url = f"{self.base_api_url}/api/v2/routing/queues/{queue_id}/users"
        
        try:
            response = self._client.get(url, headers=self._get_headers())
            response.raise_for_status()
            users = response.json().get("entities", [])
            print(f"Found {len(users)} user(s) in the queue.")
            return users
        except httpx.HTTPStatusError as e:
            print(f"Error fetching users: {e.response.status_code} - {e.response.text}")
            return []

    def get_user_statuses(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetches the current presence and routing status for a list of user IDs.
        """
        if not user_ids:
            return []
            
        print("Fetching user statuses...")
        url = f"{self.base_api_url}/api/v2/users/presences/purecloud/bulk"
        
        try:
            response = self._client.post(url, headers=self._get_headers(), json={"id": user_ids})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error fetching user statuses: {e.response.status_code} - {e.response.text}")
            return []


def main():
    """
    Main function to run the client.
    """
    # --- Configuration ---
    client_id = os.getenv("GENESYS_CLOUD_CLIENT_ID")
    client_secret = os.getenv("GENESYS_CLOUD_CLIENT_SECRET")
    region = os.getenv("GENESYS_CLOUD_REGION")
    queue_name = os.getenv("TARGET_QUEUE_NAME")

    if not queue_name:
        print("Error: TARGET_QUEUE_NAME is not set in your .env file.")
        return

    try:
        # --- Initialize and Run Client ---
        client = GenesysCloudClient(client_id, client_secret, region)
        
        queue_id = client.get_queue_id_by_name(queue_name)
        if not queue_id:
            return
            
        users = client.get_users_in_queue(queue_id)
        if not users:
            print("No users to report on.")
            return
            
        user_id_map = {user['id']: user['name'] for user in users}
        user_ids = list(user_id_map.keys())
        
        statuses = client.get_user_statuses(user_ids)

        # --- Display Results using rich ---
        console = Console()
        
        if not statuses:
            console.print("[bold red]Could not retrieve user statuses.[/bold red]")
            return

        table = Table(title=f"Current Status for Queue: {queue_name}", show_header=True, header_style="bold magenta")
        table.add_column("User Name", style="dim", width=25)
        table.add_column("Status", justify="left")

        for status in statuses:
            user_name = user_id_map.get(status['id'], "Unknown User")
            presence = status.get('presenceDefinition', {}).get('systemPresence', 'N/A')
            
            # Add some color based on status
            status_color = "green"
            if presence == "OFFLINE":
                status_color = "red"
            elif presence in ["BUSY", "AWAY", "MEAL"]:
                status_color = "yellow"

            table.add_row(user_name, f"[{status_color}]{presence}[/{status_color}]")

        console.print(table)

    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
