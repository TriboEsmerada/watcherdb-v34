# WatcherDB V3.3 Standard Edition - User Guide

**SQL Server Monitoring Platform**

---

| Field | Value |
|-------|-------|
| Version | 3.3 (Standard Edition) |
| Date | April 2026 (revised 2026-04-22, S2-9 sweep) |
| Audience | DBAs, System Administrators, Operations Teams |
| Portal Languages | Portuguese, English, Spanish |
| Default Port | 8433 |

---

## Table of Contents

- [1. Introduction](#1-introduction)
  - [1.1. What is WatcherDB](#11-what-is-watcherdb)
  - [1.2. General Architecture](#12-general-architecture)
  - [1.3. System Components](#13-system-components)
  - [1.4. System Requirements](#14-system-requirements)
- [2. Installation and Initial Setup](#2-installation-and-initial-setup)
  - [2.1. Prerequisites](#21-prerequisites)
  - [2.2. Installing WatcherDB V3.3 Standard Edition](#22-installing-watcherdb-v32)
  - [2.3. Configuring the .env File](#23-configuring-the-env-file)
  - [2.4. Installing as a Windows Service](#24-installing-as-a-windows-service)
  - [2.5. Verifying the Installation](#25-verifying-the-installation)
- [3. First Login](#3-first-login)
  - [3.1. Initial Login](#31-initial-login)
  - [3.2. Changing the Admin Password](#32-changing-the-admin-password)
  - [3.3. Basic Navigation](#33-basic-navigation)
  - [3.4. Language Selection](#34-language-selection)
  - [3.5. Dark Mode and Light Mode](#35-dark-mode-and-light-mode)
- [4. KPI Dashboard](#4-kpi-dashboard)
  - [4.1. Dashboard Overview](#41-dashboard-overview)
  - [4.2. KPI Categories](#42-kpi-categories)
  - [4.3. KPI Cards](#43-kpi-cards)
  - [4.4. KPI States](#44-kpi-states)
  - [4.5. Average Collection Time](#45-average-collection-time)
  - [4.6. Filters and Search](#46-filters-and-search)
- [5. Server Tabs](#5-server-tabs)
  - [5.1. Overview](#51-overview)
  - [5.2. Always On](#52-always-on)
  - [5.3. Backup](#53-backup)
  - [5.4. Space](#54-space)
  - [5.5. Disk](#55-disk)
  - [5.6. Encrypted](#56-encrypted)
  - [5.7. CPU](#57-cpu)
  - [5.8. Memory](#58-memory)
  - [5.9. Services](#59-services)
  - [5.10. Log](#510-log)
  - [5.11. SQL Diagnostics](#511-sql-diagnostics)
  - [5.12. Security](#512-security)
  - [5.13. Users](#513-users)
  - [5.14. Jobs](#514-jobs)
- [6. Control Panel](#6-control-panel)
  - [6.1. Accessing the Control Panel](#61-accessing-the-control-panel)
  - [6.2. User Management](#62-user-management)
  - [6.3. Auth Log](#63-auth-log)
  - [6.4. Active Sessions](#64-active-sessions)
  - [6.5. Resource Monitor](#65-resource-monitor)
  - [6.6. Settings](#66-settings)
- [7. Active Directory](#7-active-directory)
  - [7.1. Multi-Domain Configuration](#71-multi-domain-configuration)
  - [7.2. DNS SRV Discovery](#72-dns-srv-discovery)
  - [7.3. LDAP Search](#73-ldap-search)
  - [7.4. Auto-Fill of User Data](#74-auto-fill-of-user-data)
  - [7.5. Bind and Kerberos Authentication](#75-bind-and-kerberos-authentication)
- [8. Additional Features](#8-additional-features)
  - [8.1. Server Search](#81-server-search)
  - [8.2. PDF Export](#82-pdf-export)
  - [8.3. Network Diagnostics](#83-network-diagnostics)
  - [8.4. Predictive Analysis](#84-predictive-analysis)
  - [8.5. DBA Copilot](#85-dba-copilot)
- [9. Security](#9-security)
  - [9.1. JWT Authentication](#91-jwt-authentication)
  - [9.2. Password Policy](#92-password-policy)
  - [9.3. Account Lockout](#93-account-lockout)
  - [9.4. Roles and Permissions](#94-roles-and-permissions)
- [10. Service Administration](#10-service-administration)
  - [10.1. Windows Service Management](#101-windows-service-management)
  - [10.2. System Logs](#102-system-logs)
  - [10.3. Service Account](#103-service-account)
  - [10.4. Configuration Backup](#104-configuration-backup)
- [11. Troubleshooting](#11-troubleshooting)
  - [11.1. Startup Issues](#111-startup-issues)
  - [11.2. Authentication Issues](#112-authentication-issues)
  - [11.3. Data Collection Issues](#113-data-collection-issues)
  - [11.4. Performance Issues](#114-performance-issues)
  - [11.5. Connectivity Issues](#115-connectivity-issues)
  - [11.6. Active Directory Issues](#116-active-directory-issues)
  - [11.7. Web Portal Issues](#117-web-portal-issues)
- [12. FAQ - Frequently Asked Questions](#12-faq---frequently-asked-questions)
- [13. Glossary](#13-glossary)
- [14. Quick Reference](#14-quick-reference)

---

---

# 1. Introduction

## 1.1. What is WatcherDB

WatcherDB V3.3 Standard Edition is a centralized monitoring platform for SQL Server instances. It enables DBA and system administration teams to monitor over 100 SQL Server instances from a single web portal, with real-time visibility into availability, performance, disk space, backups, high availability, and more.

**Key capabilities:**

- Centralized monitoring of 100+ SQL Server instances
- KPI dashboard with 6 metric categories
- 14 detailed information tabs per server
- Control panel with user management and settings
- Hybrid authentication (Local + Active Directory)
- Multi-language support (Portuguese, English, Spanish)
- PDF report export
- Predictive data growth analysis
- DBA Copilot for quick queries
- Windows Service for continuous operation

**Typical use case:**

A DBA team at an airline needs to monitor dozens of SQL Server instances spread across different datacenters. Instead of connecting to each server individually, the team opens WatcherDB and gets a consolidated view of the entire SQL Server infrastructure on a single screen.

---

## 1.2. General Architecture

WatcherDB V3.3 Standard Edition follows a two-component architecture:

```
+-------------------+        HTTPS (8433)        +---------------------------+
|                   | <-------------------------> |                           |
|   Browser (UI)    |                             |   WatcherDB V3.3 Standard Edition          |
|   - Dashboard     |                             |   (FastAPI + Uvicorn)     |
|   - Server tabs   |                             |   - REST API              |
|   - Control Panel |                             |   - HTMX Frontend         |
|                   |                             |   - Auth JWT + AD         |
+-------------------+                             +---------------------------+
                                                            |
                                                            | ODBC
                                                            | Windows Auth
                                                            v
                                                  +---------------------------+
                                                  |   SQL Server Instances    |
                                                  |   (100+ servers)          |
                                                  +---------------------------+
                                                            ^
                                                            | Periodic collection
                                                            |
                                                  +---------------------------+
                                                  |   Collector Service       |
                                                  |   (Intelligence V1)      |
                                                  |   Port 8001              |
                                                  +---------------------------+
                                                            |
                                                            | Stores KPIs
                                                            v
                                                  +---------------------------+
                                                  |   WatcherDB_Intelligence  |
                                                  |   (SQL Server DB)         |
                                                  +---------------------------+
```

**Data flow:**

1. The **Collector Service** (Intelligence V1, port 8001) connects periodically to each monitored SQL Server instance
2. It collects KPI metrics (availability, performance, space, etc.)
3. It stores the collected data in the **WatcherDB_Intelligence** database
4. **WatcherDB V3.3 Standard Edition** (port 8433) reads data from the Intelligence DB
5. It displays the metrics on the web portal for users

---

## 1.3. System Components

### WatcherDB V3.3 Standard Edition - Web Portal

| Aspect | Detail |
|--------|--------|
| Framework | FastAPI (Python) |
| Server | Uvicorn |
| Frontend | HTMX + Jinja2 Templates |
| Port | 8433 |
| Authentication | JWT + Active Directory (LDAP/Kerberos) |
| Execution | Windows Service |

### Collector Service - Intelligence V1

| Aspect | Detail |
|--------|--------|
| Function | Periodic KPI collection |
| Port | 8001 |
| Connectivity | ODBC with Windows Authentication |
| Storage | WatcherDB_Intelligence (SQL Server) |
| Frequency | Configurable per KPI type |

### WatcherDB_Intelligence - Database

| Aspect | Detail |
|--------|--------|
| Engine | SQL Server 2016+ |
| Function | Centralized metrics storage |
| Data | Historical KPIs, settings, users |
| Access | Windows Authentication |

---

## 1.4. System Requirements

### Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disk | 50 GB free | 100 GB free |
| Network | 100 Mbps | 1 Gbps |

### Software Requirements

| Software | Version |
|----------|---------|
| Operating System | Windows Server 2016 or later |
| Python | 3.11 or later |
| ODBC Driver for SQL Server | 17 or 18 |
| SQL Server (for Intelligence DB) | 2016 or later |
| Supported browser | Chrome 90+, Firefox 90+, Edge 90+ |

### Network Requirements

| Port | Protocol | Function |
|------|----------|----------|
| 8433 | HTTPS/HTTP | WatcherDB V3.3 Standard Edition Web Portal |
| 8001 | HTTP | Collector Service |
| 1433 | TCP | SQL Server connection (default) |
| 389 | TCP/UDP | LDAP (Active Directory) |
| 636 | TCP | LDAPS (Secure Active Directory) |
| 88 | TCP/UDP | Kerberos (Active Directory) |

### Required Permissions

- The WatcherDB service account requires:
  - `VIEW SERVER STATE` permission on each monitored SQL Server instance
  - Read access to system DMVs (Dynamic Management Views)
  - Domain account (for Windows Authentication)
  - `Log on as a service` permission in Windows

---

---

# 2. Installation and Initial Setup

## 2.1. Prerequisites

Before starting the installation, verify the following prerequisites:

**1. Python 3.11+ installed:**

```powershell
python --version
# Expected output: Python 3.11.x or later
```

**2. ODBC Driver installed:**

```powershell
# Check installed ODBC drivers
Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}
```

The output should include `ODBC Driver 17 for SQL Server` or `ODBC Driver 18 for SQL Server`.

**3. SQL Server 2016+ available for the Intelligence DB:**

The WatcherDB_Intelligence database must be created and accessible by the service account.

**4. Service account configured:**

- Domain account with Windows Authentication
- `VIEW SERVER STATE` permission on monitored SQL Servers
- `Log on as a service` permission in Windows

---

## 2.2. Installing WatcherDB V3.3 Standard Edition

### Step 1: Copy the files

Copy the WatcherDB folder to the installation directory:

```powershell
# Create installation directory
New-Item -ItemType Directory -Path "C:\WatcherDB" -Force

# Copy files
Copy-Item -Path ".\WATCHERDB_V3.2\*" -Destination "C:\WatcherDB\" -Recurse
```

### Step 2: Install Python dependencies

```powershell
cd C:\WatcherDB

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install main dependencies
pip install -r requirements.txt
```

**Optional dependencies:**

```powershell
# For alerting features
pip install -r requirements-alerting.txt

# For analytics features
pip install -r requirements-analytics.txt

# For development environment
pip install -r requirements-dev.txt
```

### Step 3: Verify installation

```powershell
# Test that Python can find all required modules
python -c "import fastapi; import uvicorn; import pyodbc; print('OK')"
```

---

## 2.3. Configuring the .env File

The `.env` file in the project root contains essential settings. Create or edit the file with the following parameters:

```ini
# ============================================
# WatcherDB V3.3 Standard Edition - Configuration
# ============================================

# --- Server ---
HOST=0.0.0.0
PORT=8433
WORKERS=4

# --- Intelligence Database ---
DB_SERVER=sql-server.domain.local
DB_NAME=WatcherDB_Intelligence
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUSTED_CONNECTION=yes

# --- Security ---
SECRET_KEY=generate-a-random-secret-key-here
JWT_EXPIRATION_MINUTES=480
JWT_ALGORITHM=HS256

# --- Active Directory (optional) ---
AD_ENABLED=true
AD_DOMAIN=domain.local
AD_BASE_DN=DC=domain,DC=local

# --- Logging ---
LOG_LEVEL=INFO
LOG_FILE=logs/watcherdb.log

# --- Collector ---
COLLECTOR_URL=http://localhost:8001
```

**Important:** Replace the example values with the actual values for your environment. The `SECRET_KEY` must be a long, unique, random string.

To generate a secret key:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 2.4. Installing as a Windows Service

WatcherDB V3.3 Standard Edition is designed to run as a Windows Service, ensuring it starts automatically with the operating system.

### Install the service

```powershell
cd C:\WatcherDB

# Install the service
python services/web_service/install.py install
```

### Configure the service account

1. Open `services.msc` (Win+R, type `services.msc`)
2. Find the **WatcherDB V3.3 Standard Edition** service in the list
3. Right-click and select **Properties**
4. On the **Log On** tab:
   - Select **This account**
   - Enter the domain account (e.g., `DOMAIN\svc_watcherdb`)
   - Enter the password
   - Click **OK**
5. On the **General** tab:
   - Set **Startup type** to **Automatic**
6. On the **Recovery** tab:
   - First failure: **Restart the Service**
   - Second failure: **Restart the Service**
   - Subsequent failures: **Restart the Service**
   - Reset fail count after: **1 day**
   - Restart service after: **60 seconds**

### Start the service

```powershell
# Via PowerShell
Start-Service "WatcherDB V3.3 Standard Edition"

# Or via services.msc
# Right-click the service → Start
```

### Check service status

```powershell
Get-Service "WatcherDB*" | Format-Table Name, Status, StartType
```

### Useful service management commands

```powershell
# Stop the service
Stop-Service "WatcherDB V3.3 Standard Edition"

# Restart the service
Restart-Service "WatcherDB V3.3 Standard Edition"

# Uninstall the service
python services/web_service/install.py remove
```

---

## 2.5. Verifying the Installation

After installing and starting the service, verify that everything is working:

**1. Check that the service is running:**

```powershell
Get-Service "WatcherDB*"
# Status should be "Running"
```

**2. Check that the port is listening:**

```powershell
netstat -an | findstr "8433"
# Should show "LISTENING"
```

**3. Access the portal via browser:**

Open your browser and navigate to:

```
https://server:8433/watcherdb/
```

The WatcherDB login page should appear.

**4. Check the logs:**

```powershell
# View the last lines of the log
Get-Content "C:\WatcherDB\services\web_service\logs\*.log" -Tail 20
```

The log should show startup messages without errors.

---

---

# 3. First Login

## 3.1. Initial Login

After installation, access the WatcherDB portal for the first time:

1. Open the browser (Chrome, Firefox, or Edge)
2. Navigate to `https://server:8433/watcherdb/`
3. On the login page, enter the default credentials:

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |

4. Click **Login**

```
+------------------------------------------+
|              WatcherDB V3.3 Standard Edition              |
|                                          |
|    +----------------------------------+  |
|    | Username                         |  |
|    | admin                            |  |
|    +----------------------------------+  |
|                                          |
|    +----------------------------------+  |
|    | Password                         |  |
|    | ********                         |  |
|    +----------------------------------+  |
|                                          |
|    [          Login          ]           |
|                                          |
+------------------------------------------+
```

> **SECURITY WARNING:** The default password `admin123` MUST be changed immediately after the first login. Keeping the default password is a serious security risk.

---

## 3.2. Changing the Admin Password

Immediately after the first login, change the administrator password:

1. Go to the **Control Panel** (`/watcherdb/control`)
2. Navigate to the **User Management** section
3. Find the `admin` user in the list
4. Click **Edit** (pencil icon)
5. Click **Reset Password**
6. Enter a new password that meets the security policy:

**Password requirements:**

| Requirement | Description |
|-------------|-------------|
| Minimum length | 8 characters |
| Uppercase letter | At least 1 (A-Z) |
| Lowercase letter | At least 1 (a-z) |
| Number | At least 1 (0-9) |
| Symbol | At least 1 (!@#$%^&*...) |

**Example of a strong password:** `W4tch3r@DB2026`

---

## 3.3. Basic Navigation

After logging in, the portal loads the **KPI Dashboard** as the home page.

### Interface Structure

```
+------------------------------------------------------------------+
| [Logo] WatcherDB V3.3 Standard Edition    [Search...]    [PT/EN/ES] [Mode] [User] |
+------------------------------------------------------------------+
|                                                                    |
|   KPI Dashboard                                                    |
|   +----------+ +----------+ +----------+                          |
|   | Availab. | | Perform. | | Space    |                          |
|   |  98.5%   | |  OK      | |  75%     |                          |
|   +----------+ +----------+ +----------+                          |
|   +----------+ +----------+ +----------+                          |
|   | Disk     | | Backup   | | High Av. |                          |
|   |  82%     | |  WARNING | |  OK      |                          |
|   +----------+ +----------+ +----------+                          |
|                                                                    |
|   Server List                                                      |
|   +-----------------------------------------------------+        |
|   | Server           | Status | Health | Last Collection |        |
|   | SQL-PROD-01      | OK     | 95%    | 2m ago         |        |
|   | SQL-PROD-02      | WARN   | 78%    | 1m ago         |        |
|   | SQL-DEV-01       | OK     | 92%    | 3m ago         |        |
|   +-----------------------------------------------------+        |
|                                                                    |
+------------------------------------------------------------------+
```

### Top Bar Elements

| Element | Function |
|---------|----------|
| WatcherDB Logo | Click to return to the Dashboard |
| Search Bar | Search servers by name |
| Language Selector | Switch between PT/EN/ES |
| Mode Button | Toggle between dark and light mode |
| User Menu | Profile, Control Panel, Logout |

### Keyboard Navigation

| Shortcut | Function |
|----------|----------|
| `Ctrl+Shift+R` | Hard refresh (fully reloads the page, opens on KPIs) |
| `Ctrl+F` | Focus on the search bar |
| `Esc` | Close modals and menus |

---

## 3.4. Language Selection

WatcherDB V3.3 Standard Edition supports three languages:

| Code | Language |
|------|----------|
| PT | Portuguese |
| EN | English |
| ES | Spanish (Espanol) |

To change the language:

1. Click the language selector in the top bar (shows the current language code, e.g., **PT**)
2. Select the desired language from the dropdown
3. The interface updates immediately (without reloading the page)

The language preference is saved in the browser (localStorage) and persists across sessions.

> **Note:** The language change is individual per user and per browser. If you use a different browser or a different computer, the language reverts to the default (Portuguese).

---

## 3.5. Dark Mode and Light Mode

The portal supports two visual themes:

| Mode | Icon | Description |
|------|------|-------------|
| Light Mode | Sun icon | White background, dark text |
| Dark Mode | Moon icon | Dark background, light text |

To toggle between modes:

1. Click the moon/sun icon in the top bar
2. The theme changes immediately

The theme preference is saved in the browser and persists across sessions.

---

---

# 4. KPI Dashboard

## 4.1. Dashboard Overview

The KPI Dashboard is the main page of WatcherDB V3.3 Standard Edition. It presents a consolidated view of the entire monitored SQL Server infrastructure, organized into six metric categories.

The dashboard updates automatically and shows:

- Aggregated status of all instances per KPI category
- Counters of instances in OK, WARNING, and CRITICAL states
- Average data collection time
- Quick access to each server for detailed analysis

---

## 4.2. KPI Categories

The dashboard organizes metrics into six main categories:

### Availability

| Aspect | Detail |
|--------|--------|
| What it monitors | Online/offline status of each SQL Server instance |
| Metrics | Percentage of instances online, uptime |
| OK | All instances are responding |
| WARNING | Some instances with high latency |
| CRITICAL | One or more instances are not responding |

### Performance

| Aspect | Detail |
|--------|--------|
| What it monitors | SQL Server performance metrics |
| Metrics | CPU, waits, batch requests/sec |
| OK | Metrics within acceptable thresholds |
| WARNING | Metrics above normal thresholds |
| CRITICAL | Metrics at critical levels affecting operations |

### Space

| Aspect | Detail |
|--------|--------|
| What it monitors | Disk space used by databases |
| Metrics | Total, used, and free space; usage percentage per filegroup |
| OK | Free space above threshold |
| WARNING | Free space below warning threshold |
| CRITICAL | Free space critically low, risk of database running out of space |

### Disk

| Aspect | Detail |
|--------|--------|
| What it monitors | Operating system volumes and drives |
| Metrics | Total and free space per volume, reclaimable space |
| OK | All volumes have sufficient space |
| WARNING | One or more volumes with limited space |
| CRITICAL | Volumes near maximum capacity |

### Backup

| Aspect | Detail |
|--------|--------|
| What it monitors | Backup status of all databases |
| Metrics | Last FULL, DIFF, LOG backup; backup gaps |
| OK | All databases have recent backups |
| WARNING | Some databases with outdated backups |
| CRITICAL | Databases with no recent backup (critical gap) |

### High Availability

| Aspect | Detail |
|--------|--------|
| What it monitors | Always On Availability Groups |
| Metrics | Synchronization status, replicas, failover events |
| OK | All AGs (Availability Groups) synchronized |
| WARNING | Synchronization delay detected |
| CRITICAL | AG with synchronization problems or replica down |

---

## 4.3. KPI Cards

Each KPI category is represented by a card on the dashboard showing:

```
+-----------------------------------+
|   [Icon]  AVAILABILITY            |
|                                   |
|         98.5%                     |
|                                   |
|   Status: OK                      |
|   Avg. collection time: 2.3s     |
|   Servers: 102/104               |
|                                   |
|   [OK: 98] [WARN: 4] [CRIT: 2]  |
+-----------------------------------+
```

**Card elements:**

| Element | Description |
|---------|-------------|
| Icon | Representative icon for the category |
| Title | Name of the KPI category |
| Main value | Aggregated metric value (percentage, count, etc.) |
| Status | Overall state: OK (green), WARNING (yellow), CRITICAL (red) |
| Avg. collection time | Average time to collect this metric from all servers |
| Counters by state | Number of servers in each state |

---

## 4.4. KPI States

KPIs use a three-state system with associated colours:

| State | Colour | Meaning | Action required |
|-------|--------|---------|-----------------|
| **OK** | Green | Everything normal, within parameters | No action needed |
| **WARNING** | Yellow/Orange | Attention needed, outside normal parameters | Investigate and plan correction |
| **CRITICAL** | Red | Critical problem requiring immediate action | Urgent action needed |

The KPI card colour reflects the worst state across all servers in that category. For example, if 100 servers are OK but 1 is CRITICAL, the card shows red.

---

## 4.5. Average Collection Time

Each KPI card includes the average collection time, which indicates how long the Collector Service takes, on average, to gather that metric from all servers.

| Time | Indication |
|------|------------|
| < 5 seconds | Normal |
| 5-15 seconds | Acceptable, some latency |
| 15-30 seconds | Slow, check network or server load |
| > 30 seconds | Abnormal, investigate cause |

High collection times may indicate:

- Network issues between WatcherDB and the SQL Servers
- Overloaded SQL Servers that are slow to respond
- Heavy collection queries (check the Collector Service)

---

## 4.6. Filters and Search

On the dashboard, you can filter and search for servers:

**Search bar (top):**
- Type the server name (or part of it)
- Results filter in real time
- Supports partial search (e.g., "PROD" finds all servers containing "PROD")

**State filters:**
- Click the [OK], [WARN], or [CRIT] counters on a card to filter servers by state in that category

---

---

# 5. Server Tabs

When selecting a server on the dashboard, a detail page opens with 14 tabs that provide complete information about the SQL Server instance.

## 5.1. Overview

The **Overview** tab presents the general status of the selected server.

### Information displayed

| Section | Content |
|---------|---------|
| Overall status | Online/Offline, uptime |
| Health Score | Health score from 0 to 100 |
| Server information | Name, SQL Server version, edition, patch level |
| Operating system | Windows version, total RAM, CPU cores |
| Databases | List of databases with status and size |
| Service status | SQL Engine, SQL Agent, etc. |
| Alert summary | WARNING and CRITICAL counters per category |

### Health Score

The Health Score is a calculated score from 0 to 100 that reflects the overall state of the server:

| Score | Classification | Colour |
|-------|----------------|--------|
| 90-100 | Excellent | Green |
| 75-89 | Good | Light green |
| 50-74 | Fair | Yellow |
| 25-49 | Poor | Orange |
| 0-24 | Critical | Red |

The Health Score considers all server metrics: availability, performance, space, backups, high availability, and security.

### Database List

The database table shows:

| Column | Description |
|--------|-------------|
| Name | Database name |
| State | ONLINE, OFFLINE, RECOVERING, SUSPECT, etc. |
| Size | Total size in GB |
| Recovery Model | FULL, SIMPLE, BULK_LOGGED |
| Compatibility | Compatibility level |
| Last FULL backup | Date and time |

---

## 5.2. Always On

The **Always On** tab shows detailed information about Availability Groups configured on the server.

### Information displayed

| Section | Content |
|---------|---------|
| Availability Groups | List of AGs with name and status |
| Replicas | Servers participating in each AG |
| Synchronization state | SYNCHRONIZED, SYNCHRONIZING, NOT SYNCHRONIZING |
| Failover Events | Failover history with date/time and reason |
| RPO/RTO | Recovery Point Objective and Recovery Time Objective |

### Availability Groups Table

```
+---------------------------------------------------------------+
| AG Name        | Role     | Sync State    | Health | Replicas |
+---------------------------------------------------------------+
| AG_Production  | PRIMARY  | SYNCHRONIZED  | OK     | 3/3      |
| AG_Reporting   | PRIMARY  | SYNCHRONIZING | WARN   | 2/3      |
+---------------------------------------------------------------+
```

### AG Detail

When expanding an Availability Group, the following is shown:

| Information | Description |
|-------------|-------------|
| Primary replica | Server that is currently the primary |
| Secondary replicas | Secondary servers with synchronization state |
| Databases in the AG | List of databases included in the AG |
| Failover mode | Automatic or Manual |
| Availability mode | Synchronous or Asynchronous |
| Endpoint URL | Mirroring URL for each replica |
| Synchronization lag | Lag in seconds/minutes of the secondary replica |

### Failover Events

The failover history shows:

| Column | Description |
|--------|-------------|
| Date/Time | When the failover occurred |
| AG | Availability Group name |
| From | Source replica (former primary) |
| To | Target replica (new primary) |
| Type | Automatic or Manual |
| Reason | Failover reason |

### RPO and RTO

| Metric | Description | Meaning |
|--------|-------------|---------|
| RPO (Recovery Point Objective) | Maximum tolerable data loss point | How much data can be lost |
| RTO (Recovery Time Objective) | Maximum recovery time | How long the system can be down |

---

## 5.3. Backup

The **Backup** tab provides a complete view of the backup status for all databases on the server.

### Information displayed

| Section | Content |
|---------|---------|
| Last backup by type | FULL, DIFFERENTIAL, LOG |
| Backup gaps | Databases without a recent backup |
| Trends | Backup size evolution over time |
| Schedule-based detection | Backup type detected based on scheduling |

### Backup Table

```
+--------------------------------------------------------------------------+
| Database      | Last FULL        | Last DIFF        | Last LOG           |
+--------------------------------------------------------------------------+
| DB_Production | 2026-04-05 02:00 | 2026-04-05 14:00 | 2026-04-06 08:15  |
| DB_Reporting  | 2026-04-05 03:00 | 2026-04-05 15:00 | 2026-04-06 08:10  |
| DB_Staging    | 2026-04-01 02:00 | NEVER            | NEVER              |
+--------------------------------------------------------------------------+
```

### Backup Types

| Type | Description | Typical frequency |
|------|-------------|-------------------|
| **FULL** | Complete backup of the entire database | Daily or weekly |
| **DIFFERENTIAL** | Only changes since the last FULL | Every 4-12 hours |
| **LOG** | Transaction log backup | Every 15-60 minutes |

### Backup Gaps

A backup "gap" indicates that a database does not have a recent backup. WatcherDB classifies gaps as follows:

| Backup type | WARNING | CRITICAL |
|-------------|---------|----------|
| FULL | > 24 hours | > 48 hours |
| DIFF | > 12 hours | > 24 hours |
| LOG | > 1 hour | > 4 hours |

> **Note:** Databases with Recovery Model = SIMPLE do not require LOG backups.

### Backup Trends

WatcherDB shows trend charts that allow you to:

- See the evolution of backup sizes over time
- Identify abnormal growth
- Plan backup storage capacity

### Schedule-Based Detection

WatcherDB automatically detects the backup schedule type based on backup history:

- Analyzes frequency patterns from the last 30 days
- Automatically classifies whether the schedule is daily, weekly, etc.
- Alerts when an expected backup does not occur within the normal window

---

## 5.4. Space

The **Space** tab monitors space used by filegroups in each database.

### Information displayed

| Section | Content |
|---------|---------|
| Filegroups | Allocated, used, and free space per filegroup |
| Growth forecast | Prediction of when space will run out |
| Shrink candidates | Files with reclaimable free space |
| Databases by size | Ranking of the largest databases |

### Filegroup Table

```
+--------------------------------------------------------------------------+
| Database     | Filegroup | File         | Allocated | Used    | Free     |
+--------------------------------------------------------------------------+
| DB_Production| PRIMARY   | DB_Prod.mdf  | 100 GB    | 82 GB   | 18 GB   |
| DB_Production| FG_DATA   | DB_Data.ndf  | 200 GB    | 175 GB  | 25 GB   |
| DB_Production| FG_INDEX  | DB_Idx.ndf   | 50 GB     | 35 GB   | 15 GB   |
+--------------------------------------------------------------------------+
```

### Growth Forecast (Predictive Analysis)

WatcherDB V3.3 Standard Edition includes predictive analysis of filegroup growth:

| Information | Description |
|-------------|-------------|
| Growth rate | GB/day, GB/week, GB/month |
| Exhaustion forecast | Estimated date when space will run out |
| Trend | Growing, stable, or decreasing |

The forecast is based on historical data from the last 30/60/90 days and uses linear regression to project future growth.

### Shrink Candidates

List of files with significant free space that may be candidates for shrink operations:

| Column | Description |
|--------|-------------|
| Database | Database name |
| File | File name |
| Free space | Amount of free space inside the file |
| Free percentage | Percentage of free space |
| Recommendation | Whether a shrink is advisable |

> **Important:** The Space tab automatically excludes TempDB from shrink candidates, as shrinking TempDB is generally counterproductive and can cause performance issues.

---

## 5.5. Disk

The **Disk** tab monitors the physical volumes and drives on the server.

### Information displayed

| Section | Content |
|---------|---------|
| Volumes | List of drives with total and free space |
| Usage per drive | Visual progress bar per drive |
| Reclaimable space | Space that can be freed per database |
| Shrink candidates | Files with significant free space |

### Volume Table

```
+--------------------------------------------------------------------------+
| Drive  | Label         | Total    | Free      | Used     | % Used       |
+--------------------------------------------------------------------------+
| C:\    | System        | 100 GB   | 35 GB     | 65 GB    | [===== ] 65% |
| D:\    | SQL Data      | 500 GB   | 125 GB    | 375 GB   | [======] 75% |
| E:\    | Backups       | 1 TB     | 400 GB    | 600 GB   | [===== ] 60% |
| F:\    | TempDB        | 200 GB   | 150 GB    | 50 GB    | [==   ] 25%  |
+--------------------------------------------------------------------------+
```

### Reclaimable Space per Database

WatcherDB calculates how much space can potentially be reclaimed in each database:

| Column | Description |
|--------|-------------|
| Database | Database name |
| Drive | Volume where it resides |
| Current size | Total file size |
| Internal free space | Free space inside the files |
| Recovery potential | Space that could be returned to the drive |

---

## 5.6. Encrypted

The **Encrypted** tab shows information about Transparent Data Encryption (TDE) and encryption certificates.

### Information displayed

| Section | Content |
|---------|---------|
| TDE Status | Encryption status per database |
| Certificates | List of certificates with expiry dates |
| Encrypted databases | Databases with TDE enabled |
| Unencrypted databases | Databases without TDE |

### TDE Table

```
+----------------------------------------------------------------------+
| Database     | TDE Status  | Algorithm | Certificate  | Expires     |
+----------------------------------------------------------------------+
| DB_Production| Encrypted   | AES_256   | TDE_Cert_01  | 2027-01-15  |
| DB_Reporting | Encrypted   | AES_256   | TDE_Cert_01  | 2027-01-15  |
| DB_Staging   | Not Encr.   | -         | -            | -           |
+----------------------------------------------------------------------+
```

### TDE Alerts

| Alert | Condition |
|-------|-----------|
| Certificate expiring | Less than 90 days until expiry |
| Certificate expired | Certificate has already expired |
| Database without TDE | Production database without encryption |
| Certificate backup | Certificate without recent backup |

---

## 5.7. CPU

The **CPU** tab monitors the CPU usage of the SQL Server process.

### Information displayed

| Section | Content |
|---------|---------|
| Current CPU | Percentage of CPU used by SQL Server |
| System CPU | Total CPU percentage of the server |
| History | CPU usage chart over time |
| Top queries | Queries with highest CPU consumption (if available) |

### CPU Chart

The chart shows two lines:

- **SQL Server Process** (blue): CPU consumed by the sqlservr.exe process
- **System Total** (grey): Total server CPU (all processes)

The difference between the two lines indicates CPU used by other processes on the server.

### CPU Thresholds

| Level | Value | Meaning |
|-------|-------|---------|
| Normal | < 60% | Normal operation |
| High | 60-80% | Attention, significant load |
| Critical | > 80% | Excessive load, investigate |
| Saturated | > 95% | Server saturated, urgent action needed |

---

## 5.8. Memory

The **Memory** tab monitors SQL Server memory usage.

### Information displayed

| Section | Content |
|---------|---------|
| SQL Server Memory | RAM used by SQL Server |
| Page Life Expectancy | Average time a page remains in the buffer cache |
| Buffer Cache Hit Ratio | Percentage of pages found in cache |
| System memory | Total and used RAM on the server |

### Memory Metrics

| Metric | Description | Ideal value |
|--------|-------------|-------------|
| **Page Life Expectancy (PLE)** | Time (in seconds) a page stays in the buffer cache | > 300 seconds |
| **Buffer Cache Hit Ratio** | Percentage of pages read from cache vs. disk | > 99% |
| **Memory Grants Pending** | Queries waiting for memory | 0 |
| **Target Server Memory** | Memory that SQL Server wants to use | Close to Max Server Memory |
| **Total Server Memory** | Memory currently in use | Close to Target |

### Memory Alerts

| Condition | Level | Meaning |
|-----------|-------|---------|
| PLE < 300 | WARNING | Buffer cache under pressure |
| PLE < 60 | CRITICAL | Buffer cache severely pressured |
| Cache Hit < 95% | WARNING | Too many disk reads |
| Memory Grants Pending > 0 | WARNING | Queries waiting for memory |

---

## 5.9. Services

The **Services** tab shows the status of SQL Server services on the server.

### Monitored services

| Service | Description |
|---------|-------------|
| SQL Server (Engine) | Main SQL Server engine |
| SQL Server Agent | Job scheduling service |
| SQL Server Browser | Instance discovery service |
| SQL Server Reporting Services | Reporting service (SSRS) |
| SQL Server Integration Services | Data integration service (SSIS) |
| SQL Server Analysis Services | Analysis service (SSAS) |
| Full-Text Search | Full-text search service |

### Service Table

```
+----------------------------------------------------------------------+
| Service                | State    | Startup   | Account             |
+----------------------------------------------------------------------+
| SQL Server (MSSQLSVR)  | Running  | Automatic | DOMAIN\svc_sql      |
| SQL Server Agent       | Running  | Automatic | DOMAIN\svc_sqlagent |
| SQL Server Browser     | Running  | Automatic | NT AUTHORITY\LOCAL   |
| SSRS                   | Stopped  | Manual    | DOMAIN\svc_ssrs     |
+----------------------------------------------------------------------+
```

### Service Alerts

| Condition | Level |
|-----------|-------|
| SQL Server Engine stopped | CRITICAL |
| SQL Server Agent stopped | WARNING |
| Service with Automatic startup but stopped | WARNING |
| Service running under incorrect account | INFO |

---

## 5.10. Log

The **Log** tab shows the SQL Server Error Log with filtering by severity.

### Information displayed

| Section | Content |
|---------|---------|
| Current Error Log | Entries from the current SQL Server log |
| Severity filter | Filter by severity level |
| Search | Free-text search in the log |
| Counters | Number of events per severity |

### Severity Levels

| Severity | Description | Colour |
|----------|-------------|--------|
| Information | Informational events | Blue |
| Warning | Warnings that need attention | Yellow |
| Error | Errors affecting operations | Red |

### Sample log entries

```
+--------------------------------------------------------------------------+
| Date/Time            | Severity    | Message                             |
+--------------------------------------------------------------------------+
| 2026-04-06 08:15:23  | Information | Database 'DB_Prod' backed up.       |
| 2026-04-06 08:10:45  | Warning     | I/O requests taking longer than 15s |
| 2026-04-06 07:55:12  | Error       | Login failed for user 'app_user'    |
+--------------------------------------------------------------------------+
```

### Usage tips

- Use the severity filter to focus on critical errors
- Search for specific text (e.g., "deadlock", "backup", "login failed")
- Logs are shown from newest to oldest
- SQL Server maintains multiple log files; WatcherDB shows the current log

---

## 5.11. SQL Diagnostics

The **SQL Diagnostics** tab is an advanced diagnostic tool that reveals performance and concurrency issues in SQL Server.

### Diagnostic sections

#### Blocking

| Information | Description |
|-------------|-------------|
| Blocked sessions | Sessions waiting for a lock |
| Blocking session | The session holding the lock |
| Wait time | How long the session has been blocked |
| Blocked query | The SQL command that is blocked |
| Blocking query | The SQL command causing the blocking |

#### Deadlocks

| Information | Description |
|-------------|-------------|
| Recent deadlocks | List of detected deadlocks |
| Victim | Session that was terminated |
| Resources involved | Tables/indexes involved in the deadlock |
| Queries | SQL commands from each session |
| Date/Time | When the deadlock occurred |

#### Slow Queries

| Information | Description |
|-------------|-------------|
| Top slow queries | Queries with the longest execution time |
| Execution time | Average and maximum duration |
| Execution count | Number of times the query was executed |
| Execution plan | Indication of whether the plan is cached |
| CPU and I/O | Resources consumed by the query |

#### Missing Indexes

| Information | Description |
|-------------|-------------|
| Suggested indexes | Indexes that SQL Server suggests creating |
| Estimated impact | Estimated performance improvement |
| Table | Table that would benefit from the index |
| Columns | Suggested columns for the index |
| Seeks/Scans | Number of seeks and scans that would benefit |

#### Sessions

| Information | Description |
|-------------|-------------|
| Active sessions | List of open sessions on SQL Server |
| SPID | Session ID (Server Process ID) |
| Login | Login name |
| Database | Current database |
| Command | Command being executed |
| State | Running, sleeping, etc. |

#### I/O Stats

| Information | Description |
|-------------|-------------|
| I/O per file | Read and write statistics per file |
| Read latency | Average read time in ms |
| Write latency | Average write time in ms |
| Stalls | Number of I/O stalls |

---

## 5.12. Security

The **Security** tab provides a view of SQL Server security.

### Information displayed

| Section | Content |
|---------|---------|
| Logins | List of server-level logins |
| Permissions | Permissions assigned to each login |
| Auditing | Audit configurations |
| Vulnerabilities | Potential security issues |

### Login Table

```
+--------------------------------------------------------------------------+
| Login            | Type     | State    | Default DB   | Last access     |
+--------------------------------------------------------------------------+
| sa               | SQL      | Disabled | master       | 2026-01-15      |
| DOMAIN\svc_sql   | Windows  | Enabled  | master       | 2026-04-06      |
| DOMAIN\DBA_Team  | Windows  | Enabled  | master       | 2026-04-06      |
| app_user         | SQL      | Enabled  | DB_Production| 2026-04-06      |
+--------------------------------------------------------------------------+
```

### Security checks

WatcherDB checks and alerts on:

| Check | Description | Level |
|-------|-------------|-------|
| 'sa' account active | The sa account should be disabled | WARNING |
| Logins without strong passwords | SQL logins with weak passwords | WARNING |
| Excessive permissions | Logins with unnecessary sysadmin | WARNING |
| Audit disabled | SQL Server Audit not configured | INFO |
| xp_cmdshell enabled | xp_cmdshell should not be enabled | WARNING |
| CLR enabled | CLR integration should be evaluated | INFO |

---

## 5.13. Users

The **Users** tab shows detailed information about SQL logins, database users, and roles.

### Information displayed

| Section | Content |
|---------|---------|
| SQL Logins | SQL Server authentication logins |
| Database Users | Users mapped per database |
| Roles | Server roles and database roles |
| Mapped Databases | Databases mapped to each login |

### SQL Logins

```
+----------------------------------------------------------------------+
| Login       | Type   | Policy | Expiration | Check Policy | Enabled  |
+----------------------------------------------------------------------+
| app_user    | SQL    | ON     | OFF        | ON           | Yes      |
| report_user | SQL    | ON     | ON         | ON           | Yes      |
| old_user    | SQL    | OFF    | OFF        | OFF          | No       |
+----------------------------------------------------------------------+
```

### Database Users and Roles

```
+----------------------------------------------------------------------+
| Database     | User          | Role          | Type                  |
+----------------------------------------------------------------------+
| DB_Production| app_user      | db_datareader | SQL_USER              |
| DB_Production| app_user      | db_datawriter | SQL_USER              |
| DB_Production| DOMAIN\DBA    | db_owner      | WINDOWS_USER          |
| DB_Reporting | report_user   | db_datareader | SQL_USER              |
+----------------------------------------------------------------------+
```

---

## 5.14. Jobs

The **Jobs** tab monitors SQL Server Agent Jobs.

### Information displayed

| Section | Content |
|---------|---------|
| Job list | All configured jobs with status |
| Failed jobs | Jobs that failed on the last execution |
| Schedule conflicts | Jobs scheduled at the same time |
| Trends | Execution and failure trends over time |

### Job Table

```
+--------------------------------------------------------------------------+
| Job Name            | State    | Last Exec.       | Duration | Result    |
+--------------------------------------------------------------------------+
| Backup_FULL_Daily   | Enabled  | 2026-04-06 02:00 | 45 min   | Succeeded |
| Backup_LOG_15min    | Enabled  | 2026-04-06 08:15 | 2 min    | Succeeded |
| Index_Maintenance   | Enabled  | 2026-04-06 03:00 | 2h 15m   | Succeeded |
| ETL_Daily           | Enabled  | 2026-04-06 06:00 | 35 min   | Failed    |
| History_Cleanup     | Disabled | 2026-03-15 02:00 | 10 min   | Succeeded |
+--------------------------------------------------------------------------+
```

### Failed Job Detail

Clicking on a failed job shows:

| Information | Description |
|-------------|-------------|
| Error message | Full error text |
| Failed step | Which step of the job failed |
| History | Last N executions with result |
| Durations | Duration comparison between executions |

### Schedule Conflicts

WatcherDB automatically detects when two or more jobs are scheduled to run at the same time or with overlap:

```
+----------------------------------------------------------------------+
| Conflict                                                              |
+----------------------------------------------------------------------+
| Backup_FULL and Index_Maintenance both scheduled for 02:00           |
| ETL_Daily (06:00-06:35) overlaps with Stats_Update (06:15-06:45)    |
+----------------------------------------------------------------------+
```

### Job Trends

Trend charts show:

- Success/failure percentage over time
- Duration evolution of each job
- Failure patterns (whether certain days/hours have more failures)

---

---

# 6. Control Panel

## 6.1. Accessing the Control Panel

The Control Panel is available at the URL:

```
https://server:8433/watcherdb/control
```

It can also be accessed through the user menu in the portal top bar.

> **Note:** Access to the Control Panel is restricted to users with the **admin** or **operator** role. Users with the **viewer** or **analyst** role cannot access it.

### Control Panel Sections

```
+------------------------------------------------------------------+
|  Control Panel                                                    |
|                                                                  |
|  +-------------------+  +-------------------+                    |
|  | User              |  | Auth Log          |                    |
|  | Management        |  | Login history      |                    |
|  +-------------------+  +-------------------+                    |
|                                                                  |
|  +-------------------+  +-------------------+                    |
|  | Active Sessions   |  | Resource Monitor  |                    |
|  | Users online      |  | CPU/RAM/Disk      |                    |
|  +-------------------+  +-------------------+                    |
|                                                                  |
|  +-------------------+                                           |
|  | Settings          |                                           |
|  | JWT, AD, Policies |                                           |
|  +-------------------+                                           |
+------------------------------------------------------------------+
```

---

## 6.2. User Management

The User Management section allows you to manage all WatcherDB accounts.

### User List

```
+--------------------------------------------------------------------------+
| Username   | Name           | Email              | Role    | Type  | State  |
+--------------------------------------------------------------------------+
| admin      | Administrator  | admin@tap.pt       | admin   | Local | Active |
| joao.silva | Joao Silva     | j.silva@tap.pt     | analyst | AD    | Active |
| maria.dba  | Maria Santos   | m.santos@tap.pt    | operator| AD    | Active |
| viewer01   | Viewer Account | viewer@tap.pt      | viewer  | Local | Locked |
+--------------------------------------------------------------------------+
```

### Creating a Local User

To create a new local user:

1. Click **New User**
2. Select type **Local**
3. Fill in the fields:

| Field | Required | Description |
|-------|----------|-------------|
| Username | Yes | Unique username |
| Full name | Yes | Display name |
| Email | No | Email address |
| Role | Yes | viewer, analyst, operator, or admin |
| Password | Yes | Must meet the password policy |

4. Click **Create**

**Password requirements:**

```
Minimum 8 characters
At least 1 uppercase letter (A-Z)
At least 1 lowercase letter (a-z)
At least 1 number (0-9)
At least 1 symbol (!@#$%^&*()-_+=[]{}|;:',.<>?/)
```

### Creating an Active Directory User

To create a new AD user:

1. Click **New User**
2. Select type **Active Directory**
3. Select the **Domain** from the dropdown (if multi-domain is configured)
4. Type the username in the search field
5. The LDAP search runs automatically (searches by sAMAccountName, cn, and displayName)
6. Select the correct user from the results
7. The **Name** and **Email** fields are auto-filled (from proxyAddresses, UPN, mail)
8. Select the **Role**
9. Click **Create**

> **Note:** AD users do not need a password in WatcherDB. Authentication is performed directly against Active Directory.

### Editing a User

To edit an existing user:

1. Click the edit icon (pencil) on the user's row
2. Editable fields:

| Field | Description |
|-------|-------------|
| Full name | Change the display name |
| Email | Change the email address |
| Role | Change the role (viewer/analyst/operator/admin) |

3. Click **Save**

### User Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| **viewer** | View only | See dashboard and server tabs (read-only) |
| **analyst** | Analyst | Viewer + export PDF reports + DBA Copilot |
| **operator** | Operator | Analyst + access to the Control Panel (partial management) |
| **admin** | Administrator | Full access, user management and settings |

### Password Reset

To reset a user's password:

1. Click **Edit** on the user
2. Click **Reset Password**
3. Enter the new password (must meet the policy)
4. Click **Confirm**
5. The user receives the `must_change_password` flag and will be required to change the password on next login

> **Note:** Password reset only applies to Local users. AD users manage their password in Active Directory.

### Deleting a User

To delete a user:

1. Click the delete icon (trash) on the user's row
2. A confirmation dialog appears:

```
+------------------------------------------+
|  Confirm deletion                        |
|                                          |
|  Are you sure you want to delete the     |
|  user "joao.silva"?                      |
|                                          |
|  This action is PERMANENT and cannot     |
|  be reversed.                            |
|                                          |
|  [Cancel]    [Delete]                    |
+------------------------------------------+
```

3. Click **Delete** to confirm

> **Warning:** Deleting a user is permanent. All active sessions for that user are terminated immediately.

### Enabling/Disabling a User

To disable a user without deleting them:

1. Click the status toggle on the user's row
2. The user is set to **Inactive** state
3. They cannot log in while inactive
4. To reactivate, click the toggle again

---

## 6.3. Auth Log

The Auth Log shows the complete history of authentication attempts on the portal.

### Information displayed

```
+--------------------------------------------------------------------------+
| Date/Time            | Username   | Result  | IP           | Details     |
+--------------------------------------------------------------------------+
| 2026-04-06 08:15:23  | admin      | Success | 10.0.1.50    |             |
| 2026-04-06 08:14:55  | joao.silva | Success | 10.0.1.51    | AD Login    |
| 2026-04-06 08:10:12  | hacker123  | Failed  | 192.168.1.99 | User not    |
|                      |            |         |              | found       |
| 2026-04-06 08:09:45  | admin      | Failed  | 192.168.1.99 | Wrong       |
|                      |            |         |              | password    |
+--------------------------------------------------------------------------+
```

### Auth Log Fields

| Field | Description |
|-------|-------------|
| Date/Time | Exact timestamp of the attempt |
| Username | Username provided |
| Result | Success or Failed |
| IP | Source IP address |
| Details | Additional information (failure reason, login type, etc.) |

### Available Filters

- **By result:** Success, Failed, All
- **By date:** Date range
- **By username:** Search by username
- **By IP:** Search by IP address

### Auth Log Uses

The Auth Log is essential for:

- **Security:** Detecting unauthorized access attempts
- **Auditing:** Recording who accessed the portal and when
- **Diagnostics:** Identifying authentication problems
- **Compliance:** Maintaining access records for audits

---

## 6.4. Active Sessions

The Active Sessions section shows all users currently online on the portal.

### Information displayed

```
+--------------------------------------------------------------------------+
| Username     | Name           | Login            | Last activity         |
+--------------------------------------------------------------------------+
| admin        | Administrator  | 2026-04-06 07:30 | 2026-04-06 08:16      |
| joao.silva   | Joao Silva     | 2026-04-06 08:15 | 2026-04-06 08:16      |
| maria.dba    | Maria Santos   | 2026-04-06 08:00 | 2026-04-06 08:14      |
+--------------------------------------------------------------------------+
```

### Heartbeat Mechanism

WatcherDB uses a heartbeat system to detect online users:

- The browser sends a heartbeat every **60 seconds**
- If no heartbeat is received within 2 minutes, the user is considered offline
- The JWT session remains valid until it expires, but the user no longer appears in the active sessions list

### Session Information

| Field | Description |
|-------|-------------|
| Username | User login name |
| Name | Full name |
| Login time | When the user logged in |
| Last activity | Last heartbeat received |
| Duration | Total session time |
| IP | User's IP address |
| Browser | Detected browser type |

---

## 6.5. Resource Monitor

The Resource Monitor shows real-time metrics of the WatcherDB process and the server it runs on.

### WatcherDB Process Metrics

| Metric | Description |
|--------|-------------|
| Process CPU | Percentage of CPU used by WatcherDB |
| RAM RSS | Resident Set Size - physical memory used |
| RAM VMS | Virtual Memory Size - virtual memory allocated |
| Threads | Number of process threads |
| Open files | Number of open files |
| Connections | Number of active network connections |
| Uptime | Time since the process started |

### Server Metrics

| Metric | Description |
|--------|-------------|
| Hostname | Server name |
| Operating system | Windows version |
| Total CPU | Number of cores and current usage |
| Total RAM | Installed RAM |
| Used RAM | RAM in use and percentage |
| Disk | Space used on volumes |

### Runtime Information

| Metric | Description |
|--------|-------------|
| Python version | Python version in use |
| Working directory | WatcherDB working directory |
| Port | Port the portal is listening on |
| PID | WatcherDB Process ID |
| Workers | Number of Uvicorn workers |

### Auto-Refresh

The Resource Monitor refreshes automatically every **10 seconds**, showing real-time metrics without needing to reload the page.

### Typical Usage

The Resource Monitor is useful for:

- **Checking WatcherDB health:** Whether the process is consuming too many resources
- **Performance diagnostics:** Identifying if the server is overloaded
- **Capacity planning:** Evaluating whether server resources are sufficient
- **Troubleshooting:** Checking for memory leaks or high CPU usage

---

## 6.6. Settings

The Settings section allows you to adjust system parameters without editing files.

### JWT (JSON Web Token)

| Parameter | Description | Default value | Limits |
|-----------|-------------|---------------|--------|
| JWT Expiration | Token validity time in minutes | 480 (8 hours) | 60-1440 minutes |

When changing JWT expiration:

- Already-issued tokens keep their original validity
- New tokens use the new duration
- Lower values are more secure but require more frequent re-authentication

### Lockout

| Parameter | Description | Default value | Options |
|-----------|-------------|---------------|---------|
| Max failed attempts | Failed attempts before lockout | 5 | 3, 5, 10 |
| Lockout time | Lockout duration in minutes | 15 | 5, 10, 15, 30, 60 |

When a user exceeds the maximum number of failed attempts:

1. The account is locked automatically
2. The Auth Log records the lockout event
3. After the lockout period, the account is unlocked automatically
4. An administrator can manually unlock the account before the timer expires

### Active Directory

Configuration of Active Directory domains for hybrid authentication:

| Parameter | Description |
|-----------|-------------|
| Domains | List of configured AD domains (cards) |
| Base DN | Base Distinguished Name for LDAP searches |
| Service Account | Service account for LDAP bind (optional) |
| DNS SRV | Enable/disable automatic DC discovery |

For more details on AD configuration, see [Section 7 - Active Directory](#7-active-directory).

### Password Policy

| Parameter | Description | Value |
|-----------|-------------|-------|
| Minimum length | Minimum number of characters | 8 |
| Uppercase required | Requires at least 1 uppercase letter | Yes |
| Lowercase required | Requires at least 1 lowercase letter | Yes |
| Digit required | Requires at least 1 number | Yes |
| Symbol required | Requires at least 1 special character | Yes |

### Settings Persistence

All settings are stored in the database (WatcherDB_Intelligence) and persist across service restarts. There is no need to restart the service after changing settings in the Control Panel.

---

---

# 7. Active Directory

## 7.1. Multi-Domain Configuration

WatcherDB V3.3 Standard Edition supports authentication against multiple Active Directory domains simultaneously.

### Display

Configured domains are displayed as **cards** in the interface:

```
+-------------------+  +-------------------+  +-------------------+
| DOMAIN-A.LOCAL    |  | DOMAIN-B.LOCAL    |  | DOMAIN-C.LOCAL    |
|                   |  |                   |  |                   |
| Status: OK        |  | Status: OK        |  | Status: Offline   |
| DCs: 3            |  | DCs: 2            |  | DCs: 0            |
| Users: 45         |  | Users: 23         |  | Users: 12         |
|                   |  |                   |  |                   |
| [Edit] [Test]     |  | [Edit] [Test]     |  | [Edit] [Test]     |
+-------------------+  +-------------------+  +-------------------+
```

### Adding a new domain

1. In the Control Panel, go to **Settings** -> **Active Directory**
2. Click **Add Domain**
3. Fill in:

| Field | Description | Example |
|-------|-------------|---------|
| Domain name | FQDN of the AD domain | domain-a.local |
| Base DN | Base Distinguished Name | DC=domain-a,DC=local |
| Service Account (optional) | Account for LDAP bind | svc_watcherdb@domain-a.local |
| Password (if service account) | Service account password | ********** |
| DNS SRV | Enable automatic discovery | Yes |
| LDAP Port | Port (389 or 636 for LDAPS) | 389 |

4. Click **Test Connection** to verify
5. Click **Save**

---

## 7.2. DNS SRV Discovery

When the DNS SRV option is enabled, WatcherDB automatically discovers available Domain Controllers (DCs) through DNS SRV records.

### How it works

1. WatcherDB performs a DNS SRV query for `_ldap._tcp.domain.local`
2. It retrieves the list of available DCs with priority and weight
3. It selects the most suitable DC (lowest priority, highest weight)
4. In case of failure, it automatically tries the next DC in the list

### Benefits of DNS SRV

- No need to manually configure DC IP addresses
- Automatic failover when a DC becomes unavailable
- Automatically follows AD infrastructure changes
- Respects priority and weight configured in DNS

### Verifying DNS SRV records

```powershell
# Check SRV records in DNS
nslookup -type=SRV _ldap._tcp.domain.local
```

---

## 7.3. LDAP Search

LDAP search in WatcherDB is flexible and supports wildcards.

### Searched fields

When creating an AD user, the search is performed simultaneously on the following attributes:

| LDAP Attribute | Description |
|----------------|-------------|
| sAMAccountName | Logon name (e.g., joao.silva) |
| cn | Common Name (e.g., Joao Silva) |
| displayName | Display name |

### How the search works

1. The administrator types the search text (e.g., "joao")
2. WatcherDB builds an LDAP filter with wildcards:
   ```
   (|(sAMAccountName=*joao*)(cn=*joao*)(displayName=*joao*))
   ```
3. The search is executed against the selected domain
4. Results are displayed in a list

### Search example

```
Search: "silva"

Results:
+----------------------------------------------------------------------+
| Username       | Name            | Email                | Department  |
+----------------------------------------------------------------------+
| joao.silva     | Joao Silva      | j.silva@tap.pt       | DBA         |
| maria.silva    | Maria Silva     | m.silva@tap.pt       | Infra       |
| pedro.silveira | Pedro Silveira  | p.silveira@tap.pt    | Dev         |
+----------------------------------------------------------------------+
```

---

## 7.4. Auto-Fill of User Data

When selecting an AD user from the search, WatcherDB automatically fills in the form fields.

### Mapped attributes

| WatcherDB Field | LDAP Source (priority) |
|-----------------|------------------------|
| Name | displayName -> cn |
| Email | proxyAddresses (SMTP:) -> mail -> userPrincipalName |

### Email logic

The email is obtained in the following priority order:

1. **proxyAddresses:** Looks for the primary address (with `SMTP:` prefix in uppercase)
2. **mail:** Direct email attribute
3. **userPrincipalName (UPN):** Used as fallback (e.g., joao.silva@domain.local)

---

## 7.5. Bind and Kerberos Authentication

WatcherDB uses a priority chain to connect to LDAP:

### Bind priority order

| Priority | Method | Description |
|----------|--------|-------------|
| 1 | Service Account | Uses the credentials of the configured service account |
| 2 | GSSAPI (Kerberos) | Uses the Kerberos ticket of the Windows service |
| 3 | Anonymous | Anonymous bind (limited functionality) |

### How it works

1. **Service Account:** If a service account is configured for the domain, this is the preferred method. It ensures consistent access.

2. **GSSAPI (Kerberos):** If there is no service account, WatcherDB attempts to use the Kerberos ticket of the Windows account under which the service is running. Requires the service to run under a domain account.

3. **Anonymous:** Last resort. Many ADs do not allow anonymous bind, so functionality may be limited.

### Recommendation

Configuring a **dedicated service account** for each domain is the most reliable and secure option:

- Create a service account in AD (e.g., `svc_watcherdb`)
- Grant read permissions in AD (Read Members, Read All Properties)
- Configure the account in WatcherDB with the password
- The account does not need administrator permissions

---

---

# 8. Additional Features

## 8.1. Server Search

The search bar at the top of the portal allows you to find servers quickly.

### Usage

1. Click on the search bar (or press `Ctrl+F`)
2. Type the server name (or part of it)
3. Results appear in real time as you type
4. Click on the desired server to open its detail

### Search features

| Feature | Description |
|---------|-------------|
| Partial search | "PROD" finds "SQL-PROD-01", "SQL-PROD-02", etc. |
| Case insensitive | "prod" and "PROD" return the same results |
| Instant search | Results appear as you type |
| Direct access | Clicking a result opens the server |

---

## 8.2. PDF Export

WatcherDB V3.3 Standard Edition allows exporting reports in PDF format.

### How to export

1. Navigate to the desired server or tab
2. Click the **Export PDF** button (document icon)
3. The PDF is generated and downloaded automatically

### PDF Content

| Section | Content included |
|---------|------------------|
| Header | Server name, generation date/time |
| Summary | Health Score, overall status |
| KPIs | Main metrics |
| Details | Data from the active tab |
| Footer | WatcherDB information, page number |

### Requirements

- Minimum role: **analyst** (viewers cannot export)
- The PDF is generated on the server and sent to the browser
- Large files (with a lot of data) may take a few seconds

---

## 8.3. Network Diagnostics

The Network Diagnostics feature allows you to verify connectivity between WatcherDB and the SQL Server instances.

### Features

| Test | Description |
|------|-------------|
| Ping | ICMP test to check if the server responds |
| SQL Port | TCP connection test to port 1433 |
| Latency | Response time measurement |

### How to use

1. On the Overview tab of a server, click **Network Diagnostics**
2. WatcherDB runs the tests automatically
3. Results are displayed:

```
+----------------------------------------------------------------------+
| Test           | Result  | Detail                                    |
+----------------------------------------------------------------------+
| Ping           | OK      | Response in 2ms                           |
| Port 1433      | OK      | TCP connection established                |
| Average latency| OK      | 3.5ms (average of 5 attempts)            |
+----------------------------------------------------------------------+
```

---

## 8.4. Predictive Analysis

WatcherDB V3.3 Standard Edition includes predictive analysis capabilities for data growth.

### Filegroup Growth Forecast

Based on historical data collected by the Collector Service, WatcherDB calculates:

| Metric | Description |
|--------|-------------|
| Growth rate | Growth pace per day/week/month |
| Exhaustion date | When space will run out at the current rate |
| Trend | Whether growth is linear, accelerating, or stable |

### How it works

1. The system collects space data for each filegroup over time
2. It applies linear regression on historical data (30/60/90 days)
3. It projects future growth
4. It calculates the estimated date of space exhaustion

### Visualization

The **Space** tab for each server includes:

- Chart of used space evolution
- Projected trend line for the future
- Visual indicator of the estimated exhaustion date
- Automatic alert when exhaustion is predicted within 30 days

### Limitations

- The forecast is based on historical data and assumes linear growth
- Extraordinary events (data migration, cleanup, etc.) may change the trend
- The more historical data available, the more accurate the forecast

---

## 8.5. DBA Copilot

The DBA Copilot is a rule-based question and answer feature that helps DBAs with quick queries.

### Functionality

The DBA Copilot answers common questions about:

| Category | Example questions |
|----------|-------------------|
| Backup | "When was the last backup of DB_Production?" |
| Space | "How much free space does SQL-PROD-01 have?" |
| Performance | "Which servers have CPU above 80%?" |
| Jobs | "Which jobs failed today?" |
| Always On | "Which AGs have synchronization issues?" |
| General | "Which servers have critical alerts?" |

### How to use

1. Click the DBA Copilot icon (present on the portal)
2. Type your question in natural language
3. The Copilot analyses the question and responds with current data
4. Results include direct links to the relevant servers/tabs

### Technical note

The DBA Copilot V3.2 is **rule-based**, it does not use generative AI. Questions are mapped to predefined queries over the Intelligence DB data. AI/ML features are planned for future versions (V5).

---

---

# 9. Security

## 9.1. JWT Authentication

WatcherDB V3.3 Standard Edition uses JSON Web Tokens (JWT) for authentication.

### How it works

```
1. User sends username + password
2. WatcherDB validates credentials (Local or AD)
3. If valid, it generates a JWT signed with the SECRET_KEY
4. The JWT is sent to the browser and stored
5. Each subsequent request includes the JWT in the header
6. WatcherDB validates the JWT on each request
7. When the JWT expires, the user needs to re-authenticate
```

### JWT Structure

| Part | Content |
|------|---------|
| Header | Algorithm (HS256), type (JWT) |
| Payload | Username, role, issued at (iat), expiration (exp) |
| Signature | Signed with SECRET_KEY |

### JWT Security

| Measure | Description |
|---------|-------------|
| SECRET_KEY | Unique, random key for signing tokens |
| Expiration | Token expires after the configured time (60-1440 min) |
| Algorithm | HS256 (HMAC with SHA-256) |
| Storage | Token stored securely in the browser |

### Best practices

- Set the SECRET_KEY as a random string of at least 64 characters
- Configure JWT expiration to the minimum necessary (e.g., 480 minutes for a workday)
- Change the SECRET_KEY periodically (invalidates all existing tokens)
- Never share or expose the SECRET_KEY

---

## 9.2. Password Policy

WatcherDB V3.3 Standard Edition enforces a robust password policy for local users.

### Mandatory requirements

| Requirement | Detail |
|-------------|--------|
| Length | Minimum 8 characters |
| Uppercase | At least 1 uppercase letter (A-Z) |
| Lowercase | At least 1 lowercase letter (a-z) |
| Numbers | At least 1 digit (0-9) |
| Symbols | At least 1 special character |

### Examples

| Password | Valid | Reason |
|----------|-------|--------|
| `W4tch3r@DB` | Yes | Meets all requirements |
| `MyPassword1!` | Yes | Meets all requirements |
| `password` | No | No uppercase, number, or symbol |
| `Password1` | No | No symbol |
| `Ab1!` | No | Less than 8 characters |

### AD user passwords

Active Directory users are not affected by the WatcherDB password policy. AD password management is handled by Active Directory according to the domain GPO policies.

---

## 9.3. Account Lockout

WatcherDB implements automatic account lockout after failed login attempts.

### Configuration

| Parameter | Options | Default |
|-----------|---------|---------|
| Max attempts | 3, 5, 10 | 5 |
| Lockout time | 5, 10, 15, 30, 60 minutes | 15 minutes |

### Behaviour

1. User fails login N consecutive times
2. The account is locked automatically
3. The event is recorded in the Auth Log
4. After the lockout period, the account is unlocked automatically
5. The failed attempt counter is reset

### Manual unlock

An administrator can unlock an account before the lockout timer expires:

1. Go to the **Control Panel** -> **User Management**
2. Find the locked user (indicated as **Locked**)
3. Click **Unlock**

### Note about AD users

Account lockout in WatcherDB is independent of Active Directory lockout. An AD user can be locked in WatcherDB but not in AD (and vice versa).

---

## 9.4. Roles and Permissions

WatcherDB V3.3 Standard Edition uses a role system to control access.

### Detailed permissions table

| Feature | viewer | analyst | operator | admin |
|---------|--------|---------|----------|-------|
| View KPI Dashboard | Yes | Yes | Yes | Yes |
| View Server Tabs | Yes | Yes | Yes | Yes |
| Search Servers | Yes | Yes | Yes | Yes |
| Change language/theme | Yes | Yes | Yes | Yes |
| Export PDF | No | Yes | Yes | Yes |
| DBA Copilot | No | Yes | Yes | Yes |
| Network Diagnostics | No | No | Yes | Yes |
| Control Panel | No | No | Yes | Yes |
| User management | No | No | Partial | Yes |
| System settings | No | No | No | Yes |
| AD management | No | No | No | Yes |

### Operators vs Administrators

| Action | operator | admin |
|--------|----------|-------|
| View users | Yes | Yes |
| Create local user | Yes | Yes |
| Create AD user | No | Yes |
| Edit role to admin | No | Yes |
| Delete users | No | Yes |
| Change JWT settings | No | Yes |
| Change AD settings | No | Yes |
| Change password policy | No | Yes |

---

---

# 10. Service Administration

## 10.1. Windows Service Management

### Check status

```powershell
# Check service status
Get-Service "WatcherDB*"

# Expected output:
# Status   Name               DisplayName
# ------   ----               -----------
# Running  WatcherDB V3.3 Standard Edition     WatcherDB V3.3 Standard Edition - SQL Server Monitor
```

### Basic operations

```powershell
# Start the service
Start-Service "WatcherDB V3.3 Standard Edition"

# Stop the service
Stop-Service "WatcherDB V3.3 Standard Edition"

# Restart the service
Restart-Service "WatcherDB V3.3 Standard Edition"
```

### Check port

```powershell
# Check if port 8433 is listening
netstat -an | findstr "8433"

# Expected output:
#   TCP    0.0.0.0:8433    0.0.0.0:0    LISTENING
```

### Restart script

WatcherDB includes a PowerShell script to restart the server:

```powershell
# Use the included script
.\reiniciar_servidor.ps1
```

---

## 10.2. System Logs

WatcherDB logs are located at:

```
C:\WatcherDB\services\web_service\logs\
```

### Log files

| File | Content |
|------|---------|
| `watcherdb.log` | Main portal log |
| `service_health.txt` | Service health status |

### Log levels

| Level | Description |
|-------|-------------|
| DEBUG | Detailed information for debugging |
| INFO | Normal operational events |
| WARNING | Abnormal situations that do not prevent operation |
| ERROR | Errors that affect functionality |
| CRITICAL | Severe errors that may cause a shutdown |

### Configure log level

In the `.env` file:

```ini
# For normal operation
LOG_LEVEL=INFO

# For troubleshooting
LOG_LEVEL=DEBUG

# For production (warnings and errors only)
LOG_LEVEL=WARNING
```

### Log rotation

Logs are automatically rotated to prevent excessive growth:

- Rotation by size (when a configured limit is reached)
- Retention of N historical files
- Format: `watcherdb.log`, `watcherdb.log.1`, `watcherdb.log.2`, etc.

### View logs in real time

```powershell
# View the last 50 lines and follow new entries
Get-Content "C:\WatcherDB\services\web_service\logs\watcherdb.log" -Tail 50 -Wait
```

---

## 10.3. Service Account

The account under which the WatcherDB service runs is critical for its operation.

### Account requirements

| Requirement | Reason |
|-------------|--------|
| Domain account | Required for Windows Authentication to SQL Servers |
| Log on as a service | Windows permission to run as a service |
| VIEW SERVER STATE | SQL Server permission on each monitored instance |
| Network access | Must be able to reach all SQL Servers and Domain Controllers |

### Configure the service account

1. Open `services.msc`
2. Find **WatcherDB V3.3 Standard Edition**
3. **Properties** -> **Log On** tab
4. Select **This account**
5. Enter `DOMAIN\svc_watcherdb`
6. Enter the password
7. Click **OK**

### Verify SQL Server permissions

Run on each monitored SQL Server:

```sql
-- Check if the service account has VIEW SERVER STATE
SELECT 
    p.name AS login_name,
    pe.permission_name,
    pe.state_desc
FROM sys.server_permissions pe
JOIN sys.server_principals p ON pe.grantee_principal_id = p.principal_id
WHERE p.name = 'DOMAIN\svc_watcherdb'
    AND pe.permission_name = 'VIEW SERVER STATE';
```

If the permission is missing:

```sql
-- Grant the permission
GRANT VIEW SERVER STATE TO [DOMAIN\svc_watcherdb];
```

### Verify Log on as a service

```powershell
# Check local policy
secedit /export /cfg C:\temp\secpol.cfg
Select-String "SeServiceLogonRight" C:\temp\secpol.cfg
```

---

## 10.4. Configuration Backup

### What to back up

| Component | Location | Importance |
|-----------|----------|------------|
| .env file | `C:\WatcherDB\.env` | Environment settings |
| Intelligence database | SQL Server | Historical data and settings |
| Certificates (if HTTPS) | `C:\WatcherDB\certs\` | Required for HTTPS |

### Intelligence database backup

```sql
-- FULL backup of the Intelligence DB
BACKUP DATABASE [WatcherDB_Intelligence]
TO DISK = N'C:\Backups\WatcherDB_Intelligence_FULL.bak'
WITH COMPRESSION, INIT, STATS = 10;
```

### .env file backup

```powershell
# Copy .env to a secure location
Copy-Item "C:\WatcherDB\.env" "C:\Backups\WatcherDB\.env.$(Get-Date -Format 'yyyyMMdd')"
```

### Restore

In case of a restore:

1. Restore the Intelligence database
2. Copy the `.env` file back
3. Reinstall the service if necessary
4. Start the service

---

---

# 11. Troubleshooting

## 11.1. Startup Issues

### Service does not start

**Symptom:** The WatcherDB V3.3 Standard Edition service does not start or stops immediately after starting.

**Diagnosis:**

```powershell
# 1. Check service status
Get-Service "WatcherDB*"

# 2. Check logs
Get-Content "C:\WatcherDB\services\web_service\logs\watcherdb.log" -Tail 50

# 3. Check if the port is occupied
netstat -an | findstr "8433"

# 4. Check Event Viewer
Get-EventLog -LogName System -Source "Service Control Manager" -Newest 10
```

**Common causes and solutions:**

| Cause | Solution |
|-------|----------|
| Port 8433 already in use | Stop the process using the port or change the port in .env |
| .env file missing or corrupted | Check and fix the .env file |
| Missing Python dependencies | Run `pip install -r requirements.txt` |
| Service account without permission | Check `Log on as a service` in services.msc |
| Syntax error in configuration | Check logs for specific error message |
| Intelligence database unreachable | Check SQL Server connection |

### Port occupied

```powershell
# Find the process using port 8433
netstat -ano | findstr "8433"

# The last number is the PID. To see the process:
Get-Process -Id <PID>

# To terminate the process (with caution):
Stop-Process -Id <PID> -Force
```

---

## 11.2. Authentication Issues

### Login fails with correct credentials

**Diagnosis:**

1. Check the **Auth Log** in the Control Panel for the exact failure reason
2. Check if the account is locked (lockout)
3. For AD users, check if the domain is reachable

**Common causes:**

| Cause | Solution |
|-------|----------|
| Account locked (lockout) | Wait for the lockout period or unlock in the Control Panel |
| Expired password (AD) | Change the password in Active Directory |
| AD domain unreachable | Check network and DNS |
| must_change_password active | The user must change the password at login |
| Expired JWT | Log out and log in again |

### AD login fails

```powershell
# 1. Check if the DC responds
Test-Connection dc01.domain.local -Count 2

# 2. Check DNS SRV
nslookup -type=SRV _ldap._tcp.domain.local

# 3. Check LDAP port
Test-NetConnection dc01.domain.local -Port 389

# 4. Check Kerberos ticket
klist
```

### WatcherDB service account

If login fails for all AD users:

1. Open `services.msc`
2. Check the account on the **Log On** tab of the WatcherDB service
3. Check if the account password has not expired
4. Test the account manually:
   ```powershell
   runas /user:DOMAIN\svc_watcherdb "cmd /c echo Login OK"
   ```

---

## 11.3. Data Collection Issues

### Empty or outdated KPIs

**Symptom:** The dashboard shows KPIs with no data or old data.

**Diagnosis:**

```powershell
# 1. Check if the Collector Service is running
Get-Service "WatcherDB*Intelligence*"

# 2. Check connection to Intelligence DB
sqlcmd -S sql-server -d WatcherDB_Intelligence -Q "SELECT TOP 1 * FROM dbo.kpi_collection_log ORDER BY collection_time DESC"

# 3. Check Collector logs
Get-Content "C:\WatcherDB\services\collector\logs\*.log" -Tail 50
```

**Common causes:**

| Cause | Solution |
|-------|----------|
| Collector Service stopped | Start the Collector service |
| Intelligence DB unreachable | Check SQL Server connection |
| Service account without permissions | Check VIEW SERVER STATE on SQL Servers |
| Monitored SQL Server offline | Check if the target server is online |
| Network between Collector and SQL Servers | Check connectivity (ping, port 1433) |

### Check recent collections

```sql
-- In the Intelligence DB
SELECT TOP 20
    server_name,
    kpi_category,
    collection_time,
    duration_ms,
    status
FROM dbo.kpi_collection_log
ORDER BY collection_time DESC;
```

---

## 11.4. Performance Issues

### Slow portal

**Symptom:** The web portal responds slowly or pages take a long time to load.

**Diagnosis:**

1. Check the **Resource Monitor** in the Control Panel
2. Analyse the server load

**Common causes and solutions:**

| Cause | Indicator | Solution |
|-------|-----------|----------|
| High WatcherDB CPU | Process CPU > 80% in Resource Monitor | Check heavy queries, increase workers |
| Insufficient RAM | RAM > 90% used | Add RAM or optimize |
| Slow disk | High I/O wait | Check disk, consider SSD |
| Too many concurrent users | Many active sessions | Increase workers in .env |
| Slow Intelligence DB | Collections with high duration | Optimize indexes in the Intelligence DB |
| Slow network | High latency in Network Diagnostics | Check network infrastructure |

### Performance optimization

```ini
# In the .env file, increase workers
WORKERS=8  # default 4, increase if needed

# Or in the .env file, adjust logging
LOG_LEVEL=WARNING  # reduce logging in production
```

---

## 11.5. Connectivity Issues

### SQL Server unreachable

```powershell
# 1. Ping the server
Test-Connection sql-server-01 -Count 4

# 2. Check SQL Server port
Test-NetConnection sql-server-01 -Port 1433

# 3. Check DNS
nslookup sql-server-01

# 4. Test ODBC connection
sqlcmd -S sql-server-01 -E -Q "SELECT @@SERVERNAME, @@VERSION"
```

### Firewall

Check that the required ports are open:

```powershell
# Check firewall rules
Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*SQL*" -or $_.DisplayName -like "*WatcherDB*"}
```

Ports that must be open:

| Port | Direction | Purpose |
|------|-----------|---------|
| 8433 | Inbound | WatcherDB Web Portal |
| 1433 | Outbound | Connection to SQL Servers |
| 389 | Outbound | LDAP for Active Directory |
| 636 | Outbound | LDAPS (secure AD) |
| 88 | Outbound | Kerberos |
| 53 | Outbound | DNS |

---

## 11.6. Active Directory Issues

### LDAP search returns no results

**Common causes:**

| Cause | Solution |
|-------|----------|
| Incorrect Base DN | Check the base Distinguished Name (DC=domain,DC=local) |
| Service account without LDAP permissions | Check account permissions in AD |
| Firewall blocking port 389/636 | Check firewall rules |
| DC unavailable | Check if the Domain Controller responds |
| DNS SRV not configured | Check DNS SRV records or configure DC manually |

### Test LDAP connection manually

```powershell
# Test with ldapsearch (if available)
# Or test in PowerShell:
$domain = "domain.local"
$searcher = New-Object System.DirectoryServices.DirectorySearcher
$searcher.SearchRoot = "LDAP://DC=$($domain.Replace('.',',DC='))"
$searcher.Filter = "(sAMAccountName=joao.silva)"
$results = $searcher.FindAll()
$results.Count
```

### Kerberos not working

```powershell
# Check current Kerberos tickets
klist

# Purge tickets and obtain new ones
klist purge
```

If WatcherDB runs as a service, the Kerberos ticket of the service account is used automatically. Verify that the service account is a valid domain account.

---

## 11.7. Web Portal Issues

### Blank or partially loaded page

**Solutions:**

1. **Hard refresh:** Press `Ctrl+Shift+R` to force a full reload
2. **Clear cache:** Clear the browser cache
3. **Different browser:** Test with a different browser to isolate the problem
4. **Browser console:** Open F12 -> Console to see JavaScript errors

### Session lost after navigating

WatcherDB uses localStorage for session isolation per user. If the session is lost:

1. Check if the JWT has not expired
2. Check if there are no storage issues in the browser
3. Clear localStorage and log in again:
   - F12 -> Application -> Local Storage -> Clear

### Interface not translated

If some part of the interface does not change language:

1. Do a hard refresh (`Ctrl+Shift+R`)
2. Change the language again
3. Check the browser console for errors

---

---

# 12. FAQ - Frequently Asked Questions

### 1. How many SQL Server instances can I monitor with WatcherDB?

WatcherDB V3.3 Standard Edition is designed to monitor **100+ SQL Server instances** from a single portal. The practical limit depends on the resources of the server where WatcherDB is installed. With the recommended requirements (8 cores, 16 GB RAM), it is possible to comfortably monitor 150-200 instances.

---

### 2. Does WatcherDB work with SQL Server Express?

Yes, WatcherDB can monitor **SQL Server Express** instances. However, since SQL Server Express does not include SQL Server Agent, the **Jobs** tab will show empty data for those instances. All other features (space, backup, CPU, memory, etc.) work normally.

---

### 3. Do I need the Collector Service for the portal to work?

Yes and no. The portal (V3.2) can start and run without the Collector Service, but the **KPIs on the dashboard** will be empty or outdated, since they are collected by the Collector Service and stored in the Intelligence DB. Data that the portal reads in real time directly from SQL Servers (such as CPU, Memory tabs, etc.) will continue to work.

---

### 4. How do I add a new SQL Server to monitoring?

Adding new servers is done in the **WatcherDB_Intelligence** database. Consult the Intelligence DB administration guide or use the scripts provided in the `deploy/` folder to register new instances. After registration, the Collector begins collecting data automatically and the server appears on the dashboard.

---

### 5. Does WatcherDB support HTTPS?

WatcherDB V3.3 Standard Edition can be configured for HTTPS. To do so:

1. Obtain an SSL certificate (self-signed or from a CA)
2. Configure the certificate and key path in the `.env` file
3. Restart the service

Alternatively, you can use a reverse proxy (IIS, nginx) in front of WatcherDB for SSL termination.

---

### 6. Can I have multiple users with the admin role?

Yes, there is no limit on the number of administrators. However, as a security best practice, it is recommended to:

- Keep the minimum number of admin accounts necessary
- Use named accounts (not shared)
- Record who has admin access and review periodically

---

### 7. What happens when the JWT expires during an active session?

When the JWT token expires:

1. The next request to the server will be rejected with an authentication error
2. The portal automatically redirects to the login page
3. The user needs to log in again
4. There is no data loss; the user simply re-authenticates

To avoid frequent expirations during working hours, configure JWT Expiration to at least 480 minutes (8 hours).

---

### 8. Does WatcherDB affect the performance of the monitored SQL Servers?

The impact is **minimal**. WatcherDB uses:

- **System DMVs** (Dynamic Management Views), which are lightweight queries
- **READ UNCOMMITTED** isolation level to avoid causing blocking
- **Configurable collection intervals** to not overload the servers
- The `VIEW SERVER STATE` permission does not allow changes to the servers

The typical overhead is less than 1% CPU on each monitored SQL Server.

---

### 9. Can I run WatcherDB in Docker?

The project includes a `Dockerfile` and `docker-compose.yml` for container execution. However, the main version is optimized for **Windows Service** due to the dependency on Windows Authentication (ODBC with Trusted Connection) to access SQL Servers. Running in Docker may require additional Kerberos configurations.

---

### 10. How do I upgrade from a previous version to V3.2?

The typical upgrade process is:

1. **Backup:** Back up the Intelligence database and the `.env` file
2. **Stop the service:** `Stop-Service "WatcherDB V3.3 Standard Edition"`
3. **Replace files:** Copy the new files to `C:\WatcherDB\` (preserving the `.env`)
4. **Update dependencies:** `pip install -r requirements.txt`
5. **DB migrations:** Run `alembic upgrade head` if there are database migrations
6. **Start the service:** `Start-Service "WatcherDB V3.3 Standard Edition"`
7. **Verify:** Access the portal and verify that everything works

Consult the `CHANGELOG` in the `docs/changelog/` folder for version notes.

---

---

# 13. Glossary

| Term | Definition |
|------|------------|
| **AG** | Availability Group - SQL Server high availability group |
| **Always On** | SQL Server high availability technology based on AGs |
| **Base DN** | Base Distinguished Name for LDAP searches in Active Directory |
| **Buffer Cache** | Memory area where SQL Server stores data pages read from disk |
| **Collector Service** | Component that periodically collects metrics from SQL Servers |
| **CRITICAL** | Maximum alert state requiring immediate action |
| **Dashboard** | Main page with a consolidated view of KPIs |
| **DC** | Domain Controller - server that manages Active Directory |
| **DIFF** | Differential Backup - backup of changes since the last FULL only |
| **DMV** | Dynamic Management View - SQL Server system view for monitoring metrics |
| **DNS SRV** | DNS record that allows automatic service discovery (such as DCs) |
| **Failover** | Automatic or manual transfer of operations between replicas |
| **Filegroup** | Logical grouping of data files in SQL Server |
| **FULL** | Full backup of the entire database |
| **GSSAPI** | Generic Security Services API - interface for Kerberos authentication |
| **Health Score** | Score from 0 to 100 reflecting the overall health of a server |
| **Heartbeat** | Periodic signal sent by the browser to indicate the user is active |
| **HTMX** | JavaScript library for dynamic server interactions |
| **Intelligence DB** | WatcherDB_Intelligence database that stores collected metrics |
| **JWT** | JSON Web Token - token-based authentication mechanism |
| **Kerberos** | Authentication protocol used by Active Directory |
| **KPI** | Key Performance Indicator |
| **LDAP** | Lightweight Directory Access Protocol - protocol for accessing AD |
| **LDAPS** | LDAP over SSL/TLS (port 636) |
| **Lockout** | Temporary account lock after failed login attempts |
| **LOG** | Transaction log backup |
| **ODBC** | Open Database Connectivity - interface for accessing databases |
| **OK** | Normal state, no issues |
| **PLE** | Page Life Expectancy - average time a page stays in the buffer cache |
| **Replica** | Copy of an Availability Group on a secondary server |
| **RPO** | Recovery Point Objective - maximum tolerable data loss point |
| **RTO** | Recovery Time Objective - maximum time for recovery |
| **Shrink** | Operation that reduces the size of database files |
| **SPID** | Server Process ID - session identifier in SQL Server |
| **TDE** | Transparent Data Encryption - transparent data encryption |
| **UPN** | User Principal Name - username in the format user@domain |
| **WARNING** | Alert state that requires attention but is not urgent |

---

---

# 14. Quick Reference

## Main URLs

| URL | Function |
|-----|----------|
| `https://server:8433/watcherdb/` | Main portal (Dashboard) |
| `https://server:8433/watcherdb/control` | Control Panel |

## Keyboard Shortcuts

| Shortcut | Function |
|----------|----------|
| `Ctrl+Shift+R` | Hard refresh (reloads page, opens on KPIs) |
| `Ctrl+F` | Focus on the search bar |
| `Esc` | Close modals and menus |

## Ports

| Port | Service |
|------|---------|
| 8433 | WatcherDB V3.3 Standard Edition Web Portal |
| 8001 | Collector Service |
| 1433 | SQL Server (default) |
| 389 | LDAP |
| 636 | LDAPS |
| 88 | Kerberos |

## Useful PowerShell Commands

```powershell
# Service status
Get-Service "WatcherDB*"

# Restart service
Restart-Service "WatcherDB V3.3 Standard Edition"

# Check port
netstat -an | findstr "8433"

# View logs (last 50 lines)
Get-Content "C:\WatcherDB\services\web_service\logs\watcherdb.log" -Tail 50

# Check ODBC drivers
Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}

# Test connection to a SQL Server
Test-NetConnection sql-server-01 -Port 1433

# Check DNS SRV
nslookup -type=SRV _ldap._tcp.domain.local
```

## Default Credentials

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |

> **CHANGE IMMEDIATELY after the first login.**

## Minimum Requirements

| Resource | Value |
|----------|-------|
| OS | Windows Server 2016+ |
| Python | 3.11+ |
| ODBC | Driver 17 or 18 |
| SQL Server | 2016+ |
| RAM | 8 GB |
| CPU | 4 cores |

## File Locations

| File | Path |
|------|------|
| Configuration | `C:\WatcherDB\.env` |
| Logs | `C:\WatcherDB\services\web_service\logs\` |
| Deploy scripts | `C:\WatcherDB\deploy\` |
| Requirements | `C:\WatcherDB\requirements.txt` |

---

---

**WatcherDB V3.3 Standard Edition** - SQL Server Monitoring Platform

Developed by the DBA Team - TAP Air Portugal

April 2026
