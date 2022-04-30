CREATE TABLE IF NOT EXISTS devices (
  device_id text,
  dhcp_hostname text,
  user_key string,
  device_ip string,
  device_name string,
  device_type string,
  device_vendor string,
  device_oui string,
  ua_list string,
  suspected_pc integer,
  ts integer,
  is_inspected integer
);

CREATE INDEX IF NOT EXISTS devices_devid ON devices (
  device_id
);

CREATE TABLE IF NOT EXISTS dns (
  user_key text,
  device_id text,
  ts integer,
  ip text,
  hostname text,
  device_port integer,
  data_source text
);

CREATE INDEX IF NOT EXISTS dns_devid ON dns (
  device_id
);

CREATE TABLE IF NOT EXISTS flows (
  device_id text,
  device_port integer,
  in_byte_count real,
  is_inspected integer,
  out_byte_count real,
  protocol text,
  remote_hostname text,
  remote_hostname_info_source text,
  remote_ip text,
  remote_ip_country text,
  remote_port integer,
  remote_reg_domain text,
  remote_tracker text,
  remote_web_xray text,
  total_byte_count real,
  ts integer,
  ts_min real,
  ts_mod10 real,
  ts_mod3600 real,
  ts_mod60 real,
  ts_mod600 real,
  user_key text
);

CREATE INDEX IF NOT EXISTS flows_devid ON flows (
  device_id
);
