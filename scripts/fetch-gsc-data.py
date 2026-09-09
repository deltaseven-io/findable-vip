#!/usr/bin/env python3
"""
Fetch Google Search Console data for findable.vip case studies.
Outputs a JSON file with live stats for deltaseven.io and nwpianolessons.com.
Runs daily via GitHub Actions.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Service account credentials from GitHub secret
CREDENTIALS_JSON = os.environ.get('GSC_CREDENTIALS')
if not CREDENTIALS_JSON:
    print("ERROR: GSC_CREDENTIALS environment variable not set")
    sys.exit(1)

credentials_info = json.loads(CREDENTIALS_JSON)
credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=['https://www.googleapis.com/auth/webmasters.readonly']
)

service = build('searchconsole', 'v1', credentials=credentials)

# Properties to query — each with its own date window
# D7: baseline is from Feb 2026, so use 90-day window to show cumulative growth
# NW Piano: baseline is from Aug 29, so use 28-day window for apples-to-apples
end_date = datetime.now() - timedelta(days=3)

PROPERTIES = {
    'd7': {
        'site_url': 'sc-domain:deltaseven.io',
        'days': 90,
    },
    'nwpiano': {
        'site_url': 'sc-domain:nwpianolessons.com',
        'days': 28,
    },
}


def fetch_search_performance(site_url, start, end):
    """Fetch aggregate search performance for a property."""
    try:
        response = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                'startDate': start.strftime('%Y-%m-%d'),
                'endDate': end.strftime('%Y-%m-%d'),
                'dimensions': [],
                'rowLimit': 1
            }
        ).execute()

        if 'rows' in response and len(response['rows']) > 0:
            row = response['rows'][0]
            return {
                'impressions': int(row['impressions']),
                'clicks': int(row['clicks']),
                'ctr': round(row['ctr'] * 100, 1),
                'position': round(row['position'], 1)
            }
        return {'impressions': 0, 'clicks': 0, 'ctr': 0, 'position': 0}
    except Exception as e:
        print(f"Error fetching performance for {site_url}: {e}")
        return None


def fetch_indexed_pages(site_url):
    """Fetch indexed page count from sitemaps endpoint."""
    try:
        response = service.sitemaps().list(siteUrl=site_url).execute()
        total_indexed = 0
        if 'sitemap' in response:
            for sitemap in response['sitemap']:
                # Get the number of indexed URLs from sitemap info
                if 'contents' in sitemap:
                    for content in sitemap['contents']:
                        if content.get('indexed'):
                            total_indexed += int(content['indexed'])
        return total_indexed if total_indexed > 0 else None
    except Exception as e:
        print(f"Error fetching sitemaps for {site_url}: {e}")
        return None


def fetch_top_queries(site_url, start, end, limit=5):
    """Fetch top search queries."""
    try:
        response = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                'startDate': start.strftime('%Y-%m-%d'),
                'endDate': end.strftime('%Y-%m-%d'),
                'dimensions': ['query'],
                'rowLimit': limit,
                'orderBy': [{'fieldName': 'impressions', 'sortOrder': 'DESCENDING'}]
            }
        ).execute()

        queries = []
        if 'rows' in response:
            for row in response['rows']:
                queries.append({
                    'query': row['keys'][0],
                    'impressions': int(row['impressions']),
                    'clicks': int(row['clicks'])
                })
        return queries
    except Exception as e:
        print(f"Error fetching queries for {site_url}: {e}")
        return []


# Build the output
output = {
    'updated': datetime.now().strftime('%B %-d, %Y'),
}

for key, config in PROPERTIES.items():
    site_url = config['site_url']
    start_date = end_date - timedelta(days=config['days'])

    perf = fetch_search_performance(site_url, start_date, end_date)
    indexed = fetch_indexed_pages(site_url)

    if perf is None:
        print(f"WARNING: Could not fetch data for {site_url}, skipping")
        continue

    output[key] = {
        'period': {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d'),
        },
        'impressions': perf['impressions'],
        'clicks': perf['clicks'],
        'ctr': perf['ctr'],
        'position': perf['position'],
    }

    if indexed is not None:
        output[key]['indexed'] = indexed

    # Top queries for context
    output[key]['topQueries'] = fetch_top_queries(site_url, start_date, end_date)

# Write JSON
out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'gsc-live.json')
os.makedirs(os.path.dirname(out_path), exist_ok=True)

with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)

print(f"Written to {out_path}")
print(json.dumps(output, indent=2))
