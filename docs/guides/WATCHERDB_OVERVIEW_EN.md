# WatcherDB — Product Overview

## What is WatcherDB?

WatcherDB is an **automatic monitoring software** for SQL Server databases.

Imagine having a co-worker who works 24 hours a day, 7 days a week, watching all your database servers — checking if backups are up to date, if disk space is running low, if any service has stopped, if there are performance issues — and showing you everything on a single screen, in your browser, without needing to log into each server individually.

That is what WatcherDB does.

---

## Problem it Solves

In a company with dozens or hundreds of SQL Server instances, the database administration (DBA) team spends hours every day:

- Checking if backups on all servers completed successfully
- Checking if disk space is running low on any server
- Checking if all SQL Server services are running
- Investigating slowness or blocking issues
- Generating status reports for management

**Before WatcherDB:** The team logs into each server individually, opens tools, runs commands, and notes down the results. With 100 servers, this takes hours.

**With WatcherDB:** Everything is visible on a single web dashboard. The team can immediately see where there are problems, without logging into any server.

---

## What WatcherDB Shows

### Main Dashboard — KPI Overview

When you open WatcherDB, you see a summary of ALL servers:

| Indicator | What it means | Example |
|-----------|---------------|---------|
| **Databases available** | How many databases are online vs offline | 1,840 databases OK, 0 offline |
| **Active servers** | How many servers are responding | 75 of 82 OK, 7 offline |
| **Backups** | Whether all databases have a recent backup | 22 with missing backup |
| **Disk space** | Whether any disk is nearly full | 14 disks above 90% |
| **Performance** | Whether there are slowness issues | 1 blocked session, 5 high CPUs |
| **High availability** | Whether redundancy mechanisms are OK | All groups synchronized |

Indicators are colour-coded:
- **Green** = Everything OK
- **Yellow** = Attention needed
- **Red** = Critical problem, immediate action required

### Server Detail

Clicking on a server opens **14 different views**:

| View | What it shows |
|------|---------------|
| **Overview** | General server status |
| **High Availability** | Data redundancy and replicas |
| **Backup** | Backup history and failures |
| **Space** | Disk usage and growth forecast |
| **Disk** | Physical volumes and free space |
| **Encryption** | Encrypted databases |
| **CPU** | Processor usage |
| **Memory** | RAM usage |
| **Services** | Windows service status |
| **Log** | SQL Server error messages |
| **SQL Diagnostics** | Blocking, slowness, problematic queries |
| **Security** | Permissions and access |
| **Users** | Login accounts and permissions |
| **Scheduled Jobs** | Automated jobs and failures |

### Admin Panel

Accessible only by administrators, it allows you to:

- **Manage users** — create, edit, deactivate accounts
- **Integrate with Active Directory** — staff use the same Windows credentials
- **See who is online** — active sessions in real time
- **Monitor resources** — CPU, memory and disk of the WatcherDB server itself
- **Configure policies** — session duration, login attempts, etc.

---

## Architecture (Simplified)

```
┌──────────────┐
│   Browser    │  ← Any computer on the network
│  (Chrome)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  WatcherDB   │  ← Dedicated server (Windows Server)
│  (Portal)    │     Port 8433
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  SQL Server  │  ← The company's 100+ SQL Servers
│  Instances   │     (nothing is installed on them)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Database    │  ← Stores history and metrics
│              │     (WatcherDB Intelligence)
└──────────────┘
```

**Key points:**
- WatcherDB **does not install anything** on the servers it monitors
- It only **reads information** — it does not change anything on the servers
- All data **stays within the company** — nothing is sent to the Internet
- It works with **existing Windows credentials** — no additional passwords needed

---

## Requirements

| Component | Required |
|-----------|----------|
| **Server for WatcherDB** | 1 Windows Server machine with 16 GB RAM |
| **Network** | Access to the SQL Server instances (port 1433) |
| **Users** | A Windows domain account with read permission on the SQL Servers |
| **Browser** | Chrome, Edge, Firefox (any recent version) |

**Not required:**
- Installing software on the monitored servers
- Internet access (works fully offline)
- Third-party software licences

---

## Security

| Aspect | How it works |
|--------|--------------|
| **Portal access** | Login with username and password, or Windows credentials (Active Directory) |
| **Permissions** | 4 levels: Administrator, Operator, Analyst, Viewer |
| **Data** | Everything stays on the company's server, nothing leaves for the Internet |
| **Encryption** | Secure communication, encrypted passwords |
| **Auditing** | Automatic logging of who accessed the system and when |
| **Code protection** | Software is encrypted and protected against copying |

---

## Estimated Savings

Based on real data from a deployment with 100 servers:

| Metric | Before | With WatcherDB |
|--------|:------:|:--------------:|
| DBA hours on manual tasks/week | 30h | 10h |
| Time to detect problems | Hours | Seconds |
| Servers monitored per person | ~20 | 100+ |
| After-hours work (checks) | Frequent | Eliminated |
| **Estimated annual savings** | — | **~36,000 EUR** |

---

## Available Languages

The portal is available in:
- Portuguese
- English
- Spanish

Switching languages is instant, with no need to reload the page.

---

## Summary

WatcherDB is like having a **digital watchman** for the company's databases:

- **Sees everything** — 100+ servers on a single screen
- **Works 24/7** — no breaks, no holidays
- **Warns ahead** — detects problems before they affect the business
- **Does not interfere** — only observes, never changes anything
- **Stays in-house** — data never leaves the company

For detailed technical information, see the [User Guide](USER_GUIDE_EN.md).

---

*WatcherDB V3.3 Standard Edition — Banking-grade SQL Server Monitoring Platform*
*© 2026*
