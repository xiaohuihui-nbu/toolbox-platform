
CREATE TABLE tb_tool_settings (
	tool_id VARCHAR(64) NOT NULL, 
	enabled BOOL NOT NULL, 
	CONSTRAINT pk_tb_tool_settings PRIMARY KEY (tool_id)
)

;

CREATE TABLE tb_users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password VARCHAR(255) NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	is_admin BOOL NOT NULL, 
	enabled BOOL NOT NULL, 
	preferences JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_tb_users PRIMARY KEY (id), 
	UNIQUE (username)
)

;

CREATE TABLE tb_jobs (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	tool_id VARCHAR(64) NOT NULL, 
	tool_version VARCHAR(16) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	params JSON NOT NULL, 
	idempotency_key VARCHAR(64) NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	progress INTEGER NOT NULL, 
	attempt VARCHAR(36), 
	heartbeat_at DATETIME, 
	message TEXT NOT NULL, 
	result JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	started_at DATETIME, 
	finished_at DATETIME, 
	CONSTRAINT pk_tb_jobs PRIMARY KEY (id), 
	UNIQUE (owner_id, idempotency_key), 
	CONSTRAINT fk_tb_jobs_owner_id_tb_users FOREIGN KEY(owner_id) REFERENCES tb_users (id)
)

;

CREATE TABLE tb_assets (
	id VARCHAR(36) NOT NULL, 
	owner_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36), 
	name VARCHAR(200) NOT NULL, 
	object_key VARCHAR(255) NOT NULL, 
	size INTEGER NOT NULL, 
	mime VARCHAR(100) NOT NULL, 
	created_at DATETIME NOT NULL, 
	CONSTRAINT pk_tb_assets PRIMARY KEY (id), 
	CONSTRAINT fk_tb_assets_owner_id_tb_users FOREIGN KEY(owner_id) REFERENCES tb_users (id), 
	CONSTRAINT fk_tb_assets_job_id_tb_jobs FOREIGN KEY(job_id) REFERENCES tb_jobs (id), 
	UNIQUE (object_key)
)

;

CREATE TABLE tb_outbox (
	job_id VARCHAR(36) NOT NULL, 
	sent_at DATETIME, 
	CONSTRAINT pk_tb_outbox PRIMARY KEY (job_id), 
	CONSTRAINT fk_tb_outbox_job_id_tb_jobs FOREIGN KEY(job_id) REFERENCES tb_jobs (id)
)

;
CREATE INDEX ix_tb_job_owner_created ON tb_jobs (owner_id, created_at);
CREATE INDEX ix_tb_jobs_state ON tb_jobs (state);
CREATE INDEX ix_tb_asset_owner_created ON tb_assets (owner_id, created_at);
