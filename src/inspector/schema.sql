CREATE TABLE IF NOT EXISTS devices (
  device_id text primary key,
  dhcp_hostname text,
  user_key text,
  device_ip text,
  device_name text,
  device_type text,
  device_vendor text,
  device_oui text,
  netdisco_name text,
  fb_name text
);

CREATE TABLE IF NOT EXISTS dns (
  user_key text primary key,
  device_id text,
  ts integer,
  ip text,
  hostname text,
  device_port integer,
  data_source text
);

CREATE TABLE IF NOT EXISTS tls(
  device_id text primary key,
  user_key text,
  ts integer,
  version integer,
  sni text,
  device_ip text,
  device_port integer,
  remote_ip text,
  remote_port integer,
  cipher_suites text,
  cipher_suite_uses_grease text,
  compression_methods text,
  extension_types text,
  extension_details text,
  extension_uses_grease text
);

CREATE TABLE IF NOT EXISTS flows (
  device_id text primary key,
  user_key text,
  ts integer,
  client_ts float,
  protocol text,
  remote_ip text,
  remote_hostname text,
  remote_reg_domain text,
  remote_tracker text,
  remote_port integer,
  remote_web_xray text,
  device_port integer,
  in_byte_count float,
  out_byte_count float
);
