import os
import httpx
from dotenv import load_dotenv
from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table

# Load environment variables from a .env file
load_dotenv()

class MtaClient:
    """
    A client for interacting with the MTA backend API to get ticket information.
    """

    def __init__(self, token: str, ticket_url: str):
        """
        Initializes the MTA client.

        Args:
            token: The Bearer token for authentication.
            ticket_url: The URL to fetch tickets from.
        """
        if not all([token, ticket_url]):
            raise ValueError("Bearer Token and Ticket URL must be provided.")
            
        self._token = token
        self.ticket_url = ticket_url
        self._client = httpx.Client()

    def _get_headers(self) -> Dict[str, str]:
        """Constructs the necessary headers for API requests."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def get_tickets(self) -> List[Dict[str, Any]]:
        """
        Fetches all tickets from the configured URL.
        """
        print(f"Fetching tickets from {self.ticket_url}...")
        try:
            response = self._client.get(self.ticket_url, headers=self._get_headers())
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
            tickets = response.json()
            print(f"Successfully fetched {len(tickets)} tickets.")
            return tickets
        except httpx.HTTPStatusError as e:
            print(f"Error fetching tickets: {e.response.status_code} - {e.response.text}")
            if e.response.status_code == 401:
                print("Hint: The Bearer Token might be invalid or expired.")
            return []
        except httpx.RequestError as e:
            print(f"A network error occurred: {e}")
            return []


def filter_tickets_by_status(tickets: List[Dict[str, Any]], statuses: List[str]) -> List[Dict[str, Any]]:
    """
    Filters a list of tickets to include only those with a specific status.

    Args:
        tickets: The list of ticket dictionaries.
        statuses: A list of statuses to filter by.

    Returns:
        A new list containing only the filtered tickets.
    """
    print(f"Filtering for tickets with status in: {', '.join(statuses)}")
    filtered_list = [
        ticket for ticket in tickets if ticket.get("status") in statuses
    ]
    print(f"Found {len(filtered_list)} matching tickets.")
    return filtered_list


def main():
    """
    Main function to run the client.
    """
    # --- Configuration ---
    mta_url = os.getenv("MTA_QUEUE_TICKET_URL")
    mta_token = os.getenv("MTA_BEARER_TOKEN")
    
    # The statuses you want to see in the final report
    target_statuses = ["In Queue", "Analysis in Progress", "Updated by Customer"]

    try:
        # --- Initialize and Run Client ---
        client = MtaClient(token=mta_token, ticket_url=mta_url)
        
        all_tickets = client.get_tickets()
        if not all_tickets:
            print("No tickets were retrieved. Exiting.")
            return

        filtered_tickets = filter_tickets_by_status(all_tickets, target_statuses)

        # --- Display Results using rich ---
        console = Console()
        
        if not filtered_tickets:
            console.print("\n[bold yellow]No tickets found matching the specified statuses.[/bold yellow]")
            return

        table = Table(title="MTA Queue Tickets", show_header=True, header_style="bold blue")
        table.add_column("Ticket ID", style="dim", width=12)
        table.add_column("Customer", style="green", width=25)
        table.add_column("Title", width=40)
        table.add_column("Owner", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Severity", style="yellow")

        for ticket in filtered_tickets:
            # Add a row with data, using .get() to avoid errors if a key is missing
            table.add_row(
                ticket.get("ticketId", "N/A"),
                ticket.get("customer", "N/A"),
                ticket.get("title", "N/A"),
                ticket.get("ownerFullName", "N/A"),
                ticket.get("status", "N/A"),
                ticket.get("severity", "N/A"),
            )

        console.print(table)

    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()

