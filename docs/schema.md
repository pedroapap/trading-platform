# Trading Platform Database Schema

## Entity Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ TRADES : creates
    USERS ||--o{ STRATEGIES : creates
    USERS ||--o{ JOURNAL_ENTRIES : creates
    USERS ||--o{ BACKTESTS : creates
    USERS ||--o{ TRADE_AUDIT_LOG : "changes"
    USERS ||--o{ JOURNAL_ENTRY_VERSIONS : "edits"
    
    TRADES ||--o{ TRADE_AUDIT_LOG : "has"
    TRADES ||--o{ JOURNAL_ENTRIES : "referenced_by"
    TRADES }o--|| STRATEGIES : "follows"
    
    STRATEGIES ||--o{ STRATEGY_VERSIONS : "has"
    STRATEGIES ||--o{ BACKTESTS : "used_in"
    
    JOURNAL_ENTRIES ||--o{ JOURNAL_ENTRY_VERSIONS : "has"
    
    BACKTESTS ||--o{ BACKTEST_TRADES : "contains"
    
    MARKET_DATA : "Time-series data"

    USERS {
        uuid id PK
        string email UK
        string password_hash
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    TRADES {
        uuid id PK
        uuid user_id FK
        uuid strategy_id FK "nullable"
        string symbol
        string direction
        string status
        numeric entry_price
        timestamp entry_time
        numeric entry_size
        numeric entry_fee
        numeric exit_price "nullable"
        timestamp exit_time "nullable"
        numeric exit_size "nullable"
        numeric exit_fee
        numeric stop_loss "nullable"
        numeric take_profit "nullable"
        numeric leverage
        numeric margin_used "nullable"
        numeric liquidation_price "nullable"
        numeric pnl "calculated"
        numeric pnl_pct "calculated"
        timestamp created_at
        timestamp updated_at
        uuid updated_by FK
    }

    TRADE_AUDIT_LOG {
        uuid id PK
        uuid trade_id FK
        string event_type
        jsonb old_values
        jsonb new_values
        uuid changed_by FK
        string change_reason "nullable"
        timestamp created_at
    }

    STRATEGIES {
        uuid id PK
        uuid user_id FK
        string name
        text description "nullable"
        jsonb entry_rules
        jsonb exit_rules
        jsonb parameters "nullable"
        int version
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    STRATEGY_VERSIONS {
        uuid id PK
        uuid strategy_id FK
        int version_number
        jsonb entry_rules
        jsonb exit_rules
        jsonb parameters "nullable"
        string[] changed_fields
        timestamp created_at
    }

    JOURNAL_ENTRIES {
        uuid id PK
        uuid user_id FK
        uuid trade_id FK "nullable"
        string status
        string entry_type
        text thesis "nullable"
        text market_context "nullable"
        string emotion_state "nullable"
        text risk_assessment "nullable"
        numeric actual_pnl "nullable"
        text lessons "nullable"
        int current_version
        timestamp published_at "nullable"
        timestamp created_at
        timestamp updated_at
    }

    JOURNAL_ENTRY_VERSIONS {
        uuid id PK
        uuid journal_entry_id FK
        int version_number
        text thesis "nullable"
        text market_context "nullable"
        string emotion_state "nullable"
        text risk_assessment "nullable"
        text lessons "nullable"
        uuid edited_by FK "nullable"
        string edit_reason "nullable"
        timestamp created_at
    }

    MARKET_DATA {
        uuid id PK
        string symbol
        timestamp timestamp "clustered"
        numeric open
        numeric high
        numeric low
        numeric close
        bigint volume
        string source
        uuid import_batch_id "nullable"
        timestamp created_at
    }

    BACKTESTS {
        uuid id PK
        uuid user_id FK
        uuid strategy_id FK
        int strategy_version "FK"
        string symbol
        date date_start
        date date_end
        numeric initial_capital
        numeric position_size_pct "nullable"
        numeric slippage_pct "nullable"
        numeric commission_pct "nullable"
        numeric max_leverage
        string status
        numeric total_pnl "nullable"
        numeric total_return_pct "nullable"
        numeric sharpe_ratio "nullable"
        numeric max_drawdown_pct "nullable"
        numeric win_rate "nullable"
        int num_trades "nullable"
        text error_message "nullable"
        timestamp started_at "nullable"
        timestamp completed_at "nullable"
        timestamp created_at
    }

    BACKTEST_TRADES {
        uuid id PK
        uuid backtest_id FK
        int trade_num
        timestamp entry_time
        timestamp exit_time "nullable"
        numeric entry_price
        numeric exit_price "nullable"
        numeric size
        numeric pnl "nullable"
        numeric pnl_pct "nullable"
        numeric slippage "nullable"
        numeric fees "nullable"
        timestamp created_at
    }
```

---

## Core Schema Relationships

```
┌─────────────────────────────────────────────────────────────┐
│ DATA FLOW & OWNERSHIP                                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ USERS (root)                                                │
│ ├─ TRADES (1:N)                                            │
│ │  ├─ TRADE_AUDIT_LOG (immutable, append-only)             │
│ │  ├─ JOURNAL_ENTRIES (1:N, trades linked)                 │
│ │  │  └─ JOURNAL_ENTRY_VERSIONS (versioned history)        │
│ │  └─ STRATEGIES (referenced, optional)                     │
│ │     ├─ STRATEGY_VERSIONS (1:N, full snapshots)           │
│ │     └─ BACKTESTS (1:N, uses strategy_version)            │
│ │        └─ BACKTEST_TRADES (results per trade)            │
│                                                              │
│ MARKET_DATA (global, shared across users)                  │
│ └─ TimescaleDB hypertable (1-sec OHLCV candles)            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Complete SQL DDL

### Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_users_email ON users(email);
```

### Trades Table (Core Trading Record)
```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,
    
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('long', 'short')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('open', 'closed', 'cancelled')),
    
    -- Entry
    entry_price NUMERIC(19, 8) NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    entry_size NUMERIC(19, 8) NOT NULL,
    entry_fee NUMERIC(19, 8) DEFAULT 0,
    
    -- Exit
    exit_price NUMERIC(19, 8),
    exit_time TIMESTAMP,
    exit_size NUMERIC(19, 8),
    exit_fee NUMERIC(19, 8) DEFAULT 0,
    
    -- Risk Management
    stop_loss NUMERIC(19, 8),
    take_profit NUMERIC(19, 8),
    
    -- Leverage (Futures)
    leverage NUMERIC(10, 2) DEFAULT 1.0,
    margin_used NUMERIC(19, 8),
    liquidation_price NUMERIC(19, 8),
    
    -- Calculated Fields
    pnl NUMERIC(19, 8),
    pnl_pct NUMERIC(10, 6),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID REFERENCES users(id),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE SET NULL
);

CREATE INDEX idx_trades_user_id ON trades(user_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_entry_time ON trades(entry_time DESC);
CREATE INDEX idx_trades_status ON trades(user_id, status);
```

### Trade Audit Log (Immutable)
```sql
CREATE TABLE trade_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    
    event_type VARCHAR(50) NOT NULL CHECK (event_type IN ('entry', 'exit', 'cancel', 'update')),
    old_values JSONB,
    new_values JSONB,
    
    changed_by UUID NOT NULL REFERENCES users(id),
    change_reason VARCHAR(500),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
);

CREATE INDEX idx_trade_audit_trade_id ON trade_audit_log(trade_id);
CREATE INDEX idx_trade_audit_created_at ON trade_audit_log(created_at DESC);
```

### Strategies Table (Versioned)
```sql
CREATE TABLE strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    entry_rules JSONB NOT NULL,
    exit_rules JSONB NOT NULL,
    parameters JSONB,
    
    version INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_strategies_user_id ON strategies(user_id, is_active);
CREATE INDEX idx_strategies_updated_at ON strategies(updated_at DESC);
```

### Strategy Versions Table (Full History)
```sql
CREATE TABLE strategy_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    
    version_number INT NOT NULL,
    
    entry_rules JSONB NOT NULL,
    exit_rules JSONB NOT NULL,
    parameters JSONB,
    
    changed_fields VARCHAR[],
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE (strategy_id, version_number),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
);

CREATE INDEX idx_strategy_versions_strategy_id ON strategy_versions(strategy_id, version_number DESC);
```

### Journal Entries Table (Versioned, Immutable When Published)
```sql
CREATE TABLE journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trade_id UUID REFERENCES trades(id) ON DELETE SET NULL,
    
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    entry_type VARCHAR(50) NOT NULL CHECK (entry_type IN ('pre_trade', 'post_trade', 'note')),
    
    thesis TEXT,
    market_context TEXT,
    emotion_state VARCHAR(50) CHECK (emotion_state IN ('calm', 'greedy', 'scared', 'confused')),
    risk_assessment TEXT,
    
    actual_pnl NUMERIC(19, 8),
    lessons TEXT,
    
    current_version INT DEFAULT 1,
    published_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE (id, current_version),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE SET NULL
);

CREATE INDEX idx_journal_entries_user_id ON journal_entries(user_id);
CREATE INDEX idx_journal_entries_trade_id ON journal_entries(trade_id);
CREATE INDEX idx_journal_entries_published_at ON journal_entries(published_at DESC);
CREATE INDEX idx_journal_entries_status ON journal_entries(user_id, status);
```

### Journal Entry Versions Table (Full History + Audit)
```sql
CREATE TABLE journal_entry_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_entry_id UUID NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    
    version_number INT NOT NULL,
    
    thesis TEXT,
    market_context TEXT,
    emotion_state VARCHAR(50),
    risk_assessment TEXT,
    lessons TEXT,
    
    edited_by UUID REFERENCES users(id),
    edit_reason VARCHAR(500),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE (journal_entry_id, version_number),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE
);

CREATE INDEX idx_journal_entry_versions_entry_id ON journal_entry_versions(journal_entry_id, version_number DESC);
```

### Market Data Table (TimescaleDB Hypertable)
```sql
CREATE TABLE market_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    
    open NUMERIC(19, 8) NOT NULL,
    high NUMERIC(19, 8) NOT NULL,
    low NUMERIC(19, 8) NOT NULL,
    close NUMERIC(19, 8) NOT NULL,
    volume BIGINT NOT NULL,
    
    source VARCHAR(50) DEFAULT 'csv_import',
    import_batch_id UUID,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE (symbol, timestamp, source)
);

CREATE INDEX idx_market_data_symbol_timestamp ON market_data(symbol, timestamp DESC);

-- TimescaleDB conversion (run after table creation)
SELECT create_hypertable('market_data', 'timestamp', if_not_exists => TRUE);
```

### Backtests Table (Job Status + Results)
```sql
CREATE TABLE backtests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    strategy_version INT NOT NULL,
    
    symbol VARCHAR(20) NOT NULL,
    date_start DATE NOT NULL,
    date_end DATE NOT NULL,
    
    -- Simulation Parameters
    initial_capital NUMERIC(19, 8) NOT NULL,
    position_size_pct NUMERIC(5, 2),
    slippage_pct NUMERIC(5, 4),
    commission_pct NUMERIC(5, 4),
    max_leverage NUMERIC(10, 2) DEFAULT 1.0,
    
    -- Results
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    
    total_pnl NUMERIC(19, 8),
    total_return_pct NUMERIC(10, 6),
    sharpe_ratio NUMERIC(10, 6),
    max_drawdown_pct NUMERIC(10, 6),
    win_rate NUMERIC(5, 2),
    num_trades INT,
    
    error_message TEXT,
    
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
);

CREATE INDEX idx_backtests_user_id ON backtests(user_id, completed_at DESC);
CREATE INDEX idx_backtests_strategy_id ON backtests(strategy_id);
CREATE INDEX idx_backtests_status ON backtests(user_id, status);
```

### Backtest Trades Table (Per-Trade Results)
```sql
CREATE TABLE backtest_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id UUID NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,
    
    trade_num INT NOT NULL,
    
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    
    entry_price NUMERIC(19, 8) NOT NULL,
    exit_price NUMERIC(19, 8),
    size NUMERIC(19, 8) NOT NULL,
    
    pnl NUMERIC(19, 8),
    pnl_pct NUMERIC(10, 6),
    
    slippage NUMERIC(19, 8),
    fees NUMERIC(19, 8),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (backtest_id) REFERENCES backtests(id) ON DELETE CASCADE
);

CREATE INDEX idx_backtest_trades_backtest_id ON backtest_trades(backtest_id, trade_num);
```

---

## Index Strategy (Performance Tuning)

| Table | Index | Columns | Purpose |
|-------|-------|---------|---------|
| users | email | email | Fast login lookups |
| trades | by_user_status | user_id, status | Filter open/closed trades |
| trades | by_symbol_time | symbol, entry_time DESC | Time-series queries |
| trades | by_entry_time | entry_time DESC | Recent trades first |
| trade_audit_log | by_trade | trade_id, created_at DESC | Fetch audit history |
| strategies | by_user | user_id, is_active | List user strategies |
| strategy_versions | by_strategy | strategy_id, version_number DESC | Fetch versions |
| journal_entries | by_user_status | user_id, status | Draft vs published |
| journal_entries | by_trade | trade_id | Find entries by trade |
| journal_entries | by_date | published_at DESC | Recent entries |
| market_data | by_symbol_ts | symbol, timestamp DESC | Range queries (TimescaleDB) |
| backtests | by_user_status | user_id, status | Filter backtest jobs |
| backtest_trades | by_backtest | backtest_id, trade_num | Results per backtest |

---

## Storage Estimation

### 1-Year Single Trader (5 trades/day, BTC + ETH)

```
trades              1,825 rows ×  0.5 KB =     0.9 MB
trade_audit_log     3,650 rows ×  0.3 KB =     1.1 MB
strategies             20 rows ×  0.2 KB =     4.0 KB
strategy_versions      50 rows ×  0.2 KB =    10.0 KB
journal_entries     1,825 rows ×  0.5 KB =     0.9 MB
journal_entry_v     2,000 rows ×  0.5 KB =     1.0 MB
market_data      ~630M rows × 0.05 KB =    31.0 GB (!!!)
backtests          100 rows ×  0.5 KB =    50.0 KB
backtest_trades   5,000 rows ×  0.2 KB =     1.0 MB

TOTAL (raw):                              ~32 GB
WITH TimescaleDB compression:             ~3 GB ✓
```

**Recommendation:** 50GB SSD for 5+ years of data

---

## Schema Conventions

### Data Types
- **UUID** — Primary keys (no central sequencing needed)
- **NUMERIC(19, 8)** — Prices & P&L (arbitrary precision, no floating-point errors)
- **TIMESTAMP** — All times in UTC (application handles TZ conversion)
- **JSONB** — Flexible rule definitions (queryable, indexable)

### Immutability Patterns
- **trade_audit_log** — Never modified (pure append)
- **journal_entry_versions** — New version created on edit, published entries locked
- **strategy_versions** — New version on update, old versions archived

### Key Design Decisions
1. **Calculated fields stored** (pnl, pnl_pct) for query performance, recomputed on save
2. **JSONB for rules** allows UI flexibility without schema changes
3. **TimescaleDB hypertable** for market_data (compression + range queries)
4. **Immutability enforced at application layer** (DB allows updates, business logic prevents them for published entries)

---

## Growth Path (Phase 2+)

### Near-term (6 months)
- Add `market_data_sources` table (track API imports: IB, Binance, etc.)
- Add `risk_controls` table (per-strategy risk limits)
- Add portfolio-level aggregations (daily equity curve snapshots)

### Medium-term (1 year)
- Enable TimescaleDB compression on market_data (90% reduction)
- Partition backtests by user + date for sharding
- Archive old backtests → cold storage

### Long-term (2+ years)
- Tick-level data table (separate from OHLCV)
- Options data (Greeks, IV surfaces)
- Multi-user accounts + team collaboration tables
