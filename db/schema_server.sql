PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS panel_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  title TEXT,
  description TEXT,
  color INTEGER,
  image_url TEXT,
  purchase_grant_role_id INTEGER
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  price INTEGER NOT NULL,
  description TEXT,
  grant_role_id INTEGER,
  position INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL,
  value TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  consumed_at INTEGER,
  consumed_by INTEGER,
  order_id INTEGER,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stock_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER,
  product_name TEXT,
  category_name TEXT,
  action TEXT NOT NULL,
  qty INTEGER NOT NULL,
  before_count INTEGER NOT NULL DEFAULT 0,
  after_count INTEGER NOT NULL DEFAULT 0,
  actor_id INTEGER,
  source TEXT,
  created_at INTEGER NOT NULL,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS balances (
  user_id INTEGER PRIMARY KEY,
  balance INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  qty INTEGER NOT NULL,
  total INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  status TEXT NOT NULL,
  delivered_text TEXT,
  FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS applied_charges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  processed_at TEXT NOT NULL,
  amount INTEGER NOT NULL,
  UNIQUE(user_id, processed_at, amount)
);


CREATE TABLE IF NOT EXISTS vending_machines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category_id INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS charge_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  aos_enabled INTEGER NOT NULL DEFAULT 0,
  ios_enabled INTEGER NOT NULL DEFAULT 0,
  pushbullet_token TEXT,
  ios_log_channel_id INTEGER,
  aos_bank_name TEXT,
  aos_bank_account TEXT,
  aos_bank_owner TEXT,
  ios_bank_name TEXT,
  ios_bank_account TEXT,
  ios_bank_owner TEXT,
  charge_manager_role_id INTEGER,
  manual_charge_notice_enabled INTEGER NOT NULL DEFAULT 1,
  min_charge_amount INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ios_pending_charges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  amount INTEGER NOT NULL,
  depositor_name TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ios_webhook_dedupe (
  message_id INTEGER PRIMARY KEY,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS log_settings (
  id INTEGER PRIMARY KEY CHECK(id = 1),
  buy_channel_id INTEGER,
  buy_desc_template TEXT,
  charge_channel_id INTEGER,
  review_channel_id INTEGER,
  stock_channel_id INTEGER,
  stock_desc_template TEXT,
  manual_charge_channel_id INTEGER,
  buy_embed_color INTEGER,
  buy_image_url TEXT,
  stock_embed_color INTEGER,
  stock_image_url TEXT,
  dm_title TEXT,
  dm_desc_template TEXT,
  dm_embed_color INTEGER,
  dm_image_url TEXT,
  restock_dm_enabled INTEGER NOT NULL DEFAULT 1,
  restock_dm_template TEXT,
  login_log_channel_id INTEGER,
  stock_title_template TEXT,
  stock_everyone INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS vip_tiers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  discount_pct INTEGER NOT NULL DEFAULT 0,
  color INTEGER,
  emoji TEXT,
  position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_vip (
  user_id INTEGER PRIMARY KEY,
  tier_id INTEGER NOT NULL,
  FOREIGN KEY (tier_id) REFERENCES vip_tiers(id) ON DELETE CASCADE
);
