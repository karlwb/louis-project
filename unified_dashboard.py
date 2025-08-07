import os
from dotenv import load_dotenv
from typing import Dict, Any, List
from rich.console import Console
from rich.table import Table

# Import the refactored client classes
from genesys_client import GenesysCloudClient
from mta_client import MtaClient

# Load all environment variables from the .env file
load_dotenv()

def normalize_name(name: str) -> str:
    """
    A simple function to normalize names for fuzzy matching.
    Handles 'Last, First M.' and 'First Last' formats.
    
    Example:
    - 'Smith, Robert C' -> 'robert smith'
    - 'Bob Smith' -> 'bob smith'

    Note: This is a simplistic approach and won't handle all nickname variations
    or complex name formats, but it solves the specified problem.
    """
    if not name:
        return ""
    
    name = name.lower().strip()
    
    if ',' in name:
        # Assumes "Last, First M." format
        parts = name.split(',')
        last_name = parts[0].strip()
        first_name_parts = parts[1].strip().split()
        first_name = first_name_parts[0] # Take only the first part of the first name
        return f"{first_name} {last_name}"
    else:
        # Assumes "First Last" or similar format
        return name

def get_genesys_statuses_by_name(client: GenesysCloudClient, queue_name: str) -> Dict[str, str]:
    """
    Orchestrates the Genesys client calls to get a map of normalized names to statuses.
    """
    statuses_by_name = {}
    queue_id = client.get_queue_id_by_name(queue_name)
    if not queue_id:
        return {}
        
    users = client.get_users_in_queue(queue_id)
    if not users:
        return {}
        
    user_id_map = {user['id']: user['name'] for user in users}
    user_ids = list(user_id_map.keys())
    
    statuses = client.get_user_statuses(user_ids)
    
    for status in statuses:
        user_name = user_id_map.get(status['id'])
        if user_name:
            normalized = normalize_name(user_name)
            presence = status.get('presenceDefinition', {}).get('systemPresence', 'N/A')
            statuses_by_name[normalized] = presence
            
    return statuses_by_name

def get_filtered_mta_tickets(client: MtaClient, statuses: List[str]) -> List[Dict[str, Any]]:
    """
    Orchestrates the MTA client call and filters the tickets.
    """
    all_tickets = client.get_tickets()
    if not all_tickets:
        return []
        
    print(f"Filtering MTA tickets for status in: {', '.join(statuses)}")
    filtered_list = [
        ticket for ticket in all_tickets if ticket.get("status") in statuses
    ]
    print(f"Found {len(filtered_list)} matching MTA tickets.")
    return filtered_list

def main():
    """
    Main function to run the unified dashboard.
    """
    # --- Configuration ---
    # Genesys
    g_client_id = os.getenv("GENESYS_CLOUD_CLIENT_ID")
    g_client_secret = os.getenv("GENESYS_CLOUD_CLIENT_SECRET")
    g_region = os.getenv("GENESYS_CLOUD_REGION")
    g_queue_name = os.getenv("TARGET_QUEUE_NAME")
    
    # MTA
    mta_url = os.getenv("MTA_QUEUE_TICKET_URL")
    mta_token = os.getenv("MTA_BEARER_TOKEN")
    
    # Filter for these MTA ticket statuses
    target_mta_statuses = ["In Queue", "Analysis in Progress", "Updated by Customer"]

    console = Console()

    try:
        # --- Initialize Clients ---
        genesys_client = GenesysCloudClient(g_client_id, g_client_secret, g_region)
        mta_client = MtaClient(token=mta_token, ticket_url=mta_url)

        # --- Fetch and Process Data ---
        print("\n--- Starting Genesys Data Fetch ---")
        genesys_statuses = get_genesys_statuses_by_name(genesys_client, g_queue_name)
        if not genesys_statuses:
            console.print("[yellow]Warning: Could not retrieve any user statuses from Genesys.[/yellow]")

        print("\n--- Starting MTA Data Fetch ---")
        filtered_tickets = get_filtered_mta_tickets(mta_client, target_mta_statuses)
        if not filtered_tickets:
            console.print("\n[bold yellow]No MTA tickets found matching the specified statuses. Exiting.[/bold yellow]")
            return

        # --- Display Combined Results ---
        table = Table(title="Unified Ticket and Presence Dashboard", show_header=True, header_style="bold green")
        table.add_column("Ticket ID", style="dim", width=12)
        table.add_column("Customer", width=25)
        table.add_column("Title", width=35)
        table.add_column("Owner", style="cyan")
        table.add_column("Owner Genesys Status", justify="center")
        table.add_column("MTA Status", style="magenta")

        for ticket in filtered_tickets:
            owner_name = ticket.get("ownerFullName", "")
            normalized_owner = normalize_name(owner_name)
            
            # Find the Genesys status for the ticket owner
            owner_status = genesys_statuses.get(normalized_owner, "[grey50]N/A[/grey50]")
            
            # Add color to the status
            if owner_status == "ONLINE":
                status_cell = f"[green]{owner_status}[/green]"
            elif owner_status in ["BUSY", "AWAY", "MEAL"]:
                 status_cell = f"[yellow]{owner_status}[/yellow]"
            elif owner_status == "OFFLINE":
                status_cell = f"[red]{owner_status}[/red]"
            else:
                status_cell = owner_status # Use the default grey for N/A

            table.add_row(
                ticket.get("ticketId", "N/A"),
                ticket.get("customer", "N/A"),
                ticket.get("title", "N/A"),
                owner_name,
                status_cell,
                ticket.get("status", "N/A"),
            )
        
        console.print("\n")
        console.print(table)

    except ValueError as e:
        console.print(f"[bold red]Configuration Error: {e}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")


if __name__ == "__main__":
    main()
