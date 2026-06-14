# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "PLACEHOLDER_WORKSPACE_ID",
# META       "default_lakehouse_name": "FinOpsHub",
# META       "default_lakehouse_workspace_id": "PLACEHOLDER_WORKSPACE_ID"
# META     }
# META   }
# META }

# CELL ********************

# # GitHub Copilot Seat & Activity Data
#
# This notebook retrieves GitHub Copilot seat assignment and activity data from the GitHub API to produce an enrichment dataset for joining with the Azure FocusCost and Azure Pricing datasets.
#
# **This notebook does not calculate costs directly.** Actual charges for both GitHub Copilot and GitHub Enterprise licensing are sourced from FocusCost.
#
# This notebook provides:
# - Seat allocation and assignment data (active / inactive / never active)
# - User-level activity timestamps for reconciliation against billing periods
# - Editor usage distribution
# - Inactive seat identification for cost optimisation analysis
#
# **Data Source:** GitHub REST API (Copilot Billing endpoints)  
# **Last Updated:** June 2026

# CELL ********************

# ## Parameters
#
# Configure the notebook parameters using Fabric Variable Library for reusability across environments.

# CELL ********************

# Import required libraries
import polars as pl
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json

# CELL ********************

# Get the Variable Library
VariableLib = notebookutils.variableLibrary.getLibrary("VariableLib")

# Key Vault configuration
key_vault_url = VariableLib.key_vault_url
github_token_secret_name = VariableLib.github_token_secret_name  # Name of the secret holding the GitHub PAT

# Retrieve the GitHub PAT securely from Key Vault
GITHUB_TOKEN = notebookutils.credentials.getSecret(key_vault_url, github_token_secret_name)

# GitHub configuration
GITHUB_ORG = VariableLib.github_org  # Your GitHub organization name

# For GitHub Enterprise Server override with: https://your-enterprise.com/api/v3
# For GitHub.com or Enterprise Cloud use the default below
GITHUB_API_BASE = getattr(VariableLib, "github_api_base", "https://api.github.com")
GITHUB_API_VERSION = "2022-11-28"

# Use root path and append specific table name
finopshub_root_path = VariableLib.finopshub_root_path  # Root path: .../Tables/FinopsHub/
github_copilot_delta_table_path = f"{finopshub_root_path}/GitHubCopilotSeats"

# Print configuration values for verification
print("✓ Loaded configuration from Variable Library:")
print(f"  Key Vault URL:      {key_vault_url}")
print(f"  Token Secret Name:  {github_token_secret_name}")
print(f"  Token configured:   {'Yes' if GITHUB_TOKEN else 'No'}")
print(f"  Organization:       {GITHUB_ORG}")
print(f"  API Base URL:       {GITHUB_API_BASE}")
print(f"  Delta Table Path:   {github_copilot_delta_table_path}")

# CELL ********************

# ## Setup
#
# Import required libraries and configure the API client.

# CELL ********************

# Configure request headers for GitHub API
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": GITHUB_API_VERSION
}

def make_github_request(endpoint: str, params: Optional[Dict] = None) -> Dict:
    """
    Make authenticated request to GitHub API with error handling.
    
    Args:
        endpoint: API endpoint path (e.g., '/orgs/{org}/copilot/billing')
        params: Optional query parameters
    
    Returns:
        JSON response as dictionary
    """
    url = f"{GITHUB_API_BASE}{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"API Error {response.status_code}: {response.text}")

print("✓ API client configured")

# CELL ********************

# ## Verify Permissions
#
# Check your organization membership and role before proceeding.

# CELL ********************

# ## 1. Retrieve Billing Overview
#
# Fetch high-level billing information including total seats, active/inactive counts, and settings.

# CELL ********************

# Retrieve billing summary
billing_endpoint = f"/orgs/{GITHUB_ORG}/copilot/billing"
billing_data = make_github_request(billing_endpoint)

# Extract seat counts
seat_breakdown = billing_data.get("seat_breakdown", {})
total_seats = seat_breakdown.get("total", 0)
active_seats = seat_breakdown.get("active_this_cycle", 0)
inactive_seats = seat_breakdown.get("inactive_this_cycle", 0)
seats_added = seat_breakdown.get("added_this_cycle", 0)
seats_pending_cancellation = seat_breakdown.get("pending_cancellation", 0)
utilization_rate = (active_seats / total_seats * 100) if total_seats > 0 else 0

# Note: actual costs are sourced from FocusCost dataset - seat counts here are for reconciliation
print("=" * 60)
print("GITHUB COPILOT SEAT SUMMARY")
print("=" * 60)
print(f"\n📊 Seat Allocation (for FocusCost reconciliation):")
print(f"   Total Seats:               {total_seats:>6}")
print(f"   Active This Cycle:         {active_seats:>6}")
print(f"   Inactive This Cycle:       {inactive_seats:>6}")
print(f"   Added This Cycle:          {seats_added:>6}")
print(f"   Pending Cancellation:      {seats_pending_cancellation:>6}")
print(f"\n📈 Utilization:")
print(f"   Active Rate:               {utilization_rate:>7.1f}%")
print(f"\n🔧 Plan Type: {billing_data.get('plan_type', 'N/A').upper()}")
print("=" * 60)

# CELL ********************

# ## 2. Retrieve Detailed Seat Assignments
#
# Fetch individual seat assignments with user details and activity timestamps to identify optimization opportunities.

# CELL ********************

# Retrieve all seat assignments (handle pagination)
seats_endpoint = f"/orgs/{GITHUB_ORG}/copilot/billing/seats"
all_seats = []
page = 1
per_page = 100

print("Fetching seat assignments...")
while True:
    params = {"page": page, "per_page": per_page}
    response = make_github_request(seats_endpoint, params)
    
    seats = response.get("seats", [])
    if not seats:
        break
    
    all_seats.extend(seats)
    print(f"  Retrieved {len(all_seats)} seats...", end="\r")
    
    # Check if there are more pages
    if len(seats) < per_page:
        break
    page += 1

print(f"✓ Retrieved {len(all_seats)} total seat assignments")

# Convert to Polars DataFrame
seats_data = []
for seat in all_seats:
    assignee = seat.get("assignee", {})
    seats_data.append({
        "user_login": assignee.get("login"),
        "user_name": assignee.get("name"),
        "user_email": assignee.get("email"),
        "created_at": seat.get("created_at"),
        "updated_at": seat.get("updated_at"),
        "last_activity_at": seat.get("last_activity_at"),
        "last_activity_editor": seat.get("last_activity_editor"),
        "pending_cancellation_date": seat.get("pending_cancellation_date"),
        "assigning_team": seat.get("assigning_team", {}).get("name") if seat.get("assigning_team") else None
    })

df_seats = pl.DataFrame(seats_data)

# Convert timestamp columns to datetime
timestamp_cols = ["created_at", "updated_at", "last_activity_at", "pending_cancellation_date"]
for col in timestamp_cols:
    if col in df_seats.columns:
        df_seats = df_seats.with_columns(
            pl.col(col).str.to_datetime().alias(col)
        )

print(f"\n✓ Created DataFrame with {df_seats.height} rows × {df_seats.width} columns")
df_seats.head()

# CELL ********************

# ## 3. Analyze Seat Activity
#
# Identify inactive seats and calculate potential cost savings from optimization.

# CELL ********************

# Calculate activity metrics
current_date = datetime.now()
threshold_30_days = current_date - timedelta(days=30)
threshold_60_days = current_date - timedelta(days=60)
threshold_90_days = current_date - timedelta(days=90)

# Add activity classification columns
df_activity = df_seats.with_columns([
    # Days since last activity
    pl.when(pl.col("last_activity_at").is_not_null())
    .then((pl.lit(current_date) - pl.col("last_activity_at")).dt.total_days())
    .otherwise(None)
    .alias("days_since_activity"),

    # Activity status bands - useful for filtering when joined with FocusCost
    pl.when(pl.col("last_activity_at").is_null())
    .then(pl.lit("Never Active"))
    .when(pl.col("last_activity_at") >= threshold_30_days)
    .then(pl.lit("Active (< 30 days)"))
    .when(pl.col("last_activity_at") >= threshold_60_days)
    .then(pl.lit("Inactive (30-60 days)"))
    .when(pl.col("last_activity_at") >= threshold_90_days)
    .then(pl.lit("Inactive (60-90 days)"))
    .otherwise(pl.lit("Inactive (> 90 days)"))
    .alias("activity_status"),
])

# Aggregate by activity status
activity_summary = (
    df_activity
    .group_by("activity_status")
    .agg(pl.count().alias("seat_count"))
    .sort("seat_count", descending=True)
)

print("\n" + "=" * 60)
print("SEAT ACTIVITY ANALYSIS")
print("=" * 60)
print(activity_summary)

# Inactive seat count for reference when joining with FocusCost
inactive_seats_count = df_activity.filter(
    pl.col("activity_status").str.contains("Inactive|Never Active")
).height

print(f"\n💡 Inactive Seats (for cost optimisation in FocusCost join): {inactive_seats_count}")
print("=" * 60)

# CELL ********************

# ## 4. Identify Inactive Users
#
# List users who haven't used Copilot in 60+ days for potential seat reclamation.

# CELL ********************

# Filter for users inactive for 60+ days
# This list is the join key for identifying wasteful spend in the FocusCost dataset
df_inactive = (
    df_activity
    .filter(
        (pl.col("days_since_activity") > 60) |
        (pl.col("last_activity_at").is_null())
    )
    .select([
        "user_login",
        "user_name",
        "last_activity_at",
        "days_since_activity",
        "last_activity_editor",
        "assigning_team",
        "activity_status",
    ])
    .sort("days_since_activity", descending=True, nulls_last=False)
)

print(f"\n🔍 Found {df_inactive.height} inactive users (60+ days or never active)")
print("   Join this list against FocusCost to quantify associated spend\n")

df_inactive.head(20)

# CELL ********************

# ## 5. Editor Usage Distribution
#
# Analyze which editors are being used to understand tooling preferences.

# CELL ********************

# Analyze editor distribution (only for users with activity)
df_editor_usage = (
    df_activity
    .filter(pl.col("last_activity_editor").is_not_null())
    .group_by("last_activity_editor")
    .agg(pl.count().alias("user_count"))
    .with_columns([
        (pl.col("user_count") / pl.col("user_count").sum() * 100).round(1).alias("percentage")
    ])
    .sort("user_count", descending=True)
)

print("\n" + "=" * 60)
print("EDITOR USAGE DISTRIBUTION")
print("=" * 60)
print(df_editor_usage)
print("=" * 60)

# CELL ********************

# ## 6. Export Data for Reporting
#
# Save the seat activity enrichment data to Delta Lake for joining with the FocusCost and Azure Pricing datasets.
#
# > **Note on GitHub Enterprise costs:** GitHub Enterprise licensing charges will appear as separate line items in FocusCost. Use `total_seats` from this dataset to reconcile seat counts against those charges.

# CELL ********************

# Write seat activity enrichment data to Delta Lake
# This table is joined against FocusCost to attribute actual spend to active/inactive users
snapshot_date = datetime.now().strftime("%Y-%m-%d")

df_export = df_activity.with_columns([
    pl.lit(snapshot_date).alias("snapshot_date"),
    pl.lit(GITHUB_ORG).alias("organization")
])

df_export.write_delta(
    github_copilot_delta_table_path,
    mode="append"
)

print(f"✓ Exported {df_export.height} rows to {github_copilot_delta_table_path}")
print(f"  Snapshot date:  {snapshot_date}")
print(f"  Organization:   {GITHUB_ORG}")
print(f"  Join key for FocusCost: organization + snapshot_date")

# CELL ********************

# ## Summary
#
# Review seat allocation and activity counts. Actual spend figures (Copilot seats + GitHub Enterprise licensing) are sourced from the FocusCost dataset and joined on `organization` and billing period.

# CELL ********************

# Generate summary report
never_active = df_activity.filter(pl.col("last_activity_at").is_null()).height
inactive_30_60 = df_activity.filter(
    (pl.col("days_since_activity") > 30) & (pl.col("days_since_activity") <= 60)
).height
inactive_60_plus = df_activity.filter(pl.col("days_since_activity") > 60).height
active = df_activity.filter(pl.col("activity_status") == "Active (< 30 days)").height

print("\n" + "=" * 60)
print("SEAT ACTIVITY SUMMARY")
print("=" * 60)
print(f"\n📊 Seat Counts (reconcile against FocusCost for spend):")
print(f"   Total Seats:              {total_seats}")
print(f"   Active (< 30 days):       {active}")
print(f"   Inactive (30-60 days):    {inactive_30_60}")
print(f"   Inactive (60+ days):      {inactive_60_plus}")
print(f"   Never Active:             {never_active}")
print(f"   Utilization Rate:         {utilization_rate:.1f}%")
print(f"\n💡 Optimisation Candidates:  {inactive_seats_count} seats (inactive or never active)")
print(f"\n📋 Recommended Actions:")
print(f"   1. Join {inactive_seats_count} inactive seats against FocusCost to quantify waste")
print(f"   2. Join FocusCost Enterprise line items against total_seats for per-seat blended cost")
print(f"   3. Review {never_active} users who have never activated Copilot")
print(f"   4. Consider reclaiming inactive seats quarterly")
print("=" * 60)

# CELL ********************

# Check authenticated user and permissions
try:
    # Get authenticated user
    user_response = make_github_request("/user")
    print(f"✓ Authenticated as: {user_response.get('login')}")
    
    # Check organization membership
    membership_response = make_github_request(f"/orgs/{GITHUB_ORG}/memberships/{user_response.get('login')}")
    role = membership_response.get('role')
    state = membership_response.get('state')
    
    print(f"✓ Organization: {GITHUB_ORG}")
    print(f"✓ Your role: {role}")
    print(f"✓ Membership state: {state}")
    
    # Check if user can access billing
    if role in ['admin', 'billing_manager']:
        print("\n✅ You have access to billing information")
    else:
        print("\n⚠️  Warning: You may not have access to billing endpoints")
        print("   Required role: 'admin' (owner) or 'billing_manager'")
        
except Exception as e:
    print(f"❌ Error checking permissions: {str(e)}")
    print("   This might indicate insufficient permissions or incorrect token/org configuration")
