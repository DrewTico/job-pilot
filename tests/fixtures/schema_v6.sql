-- Genuine empty schema from c4d18f3 database.initialize_database (v6).
BEGIN TRANSACTION;
CREATE TABLE application_events (
	id VARCHAR NOT NULL,
	import_key VARCHAR,
	job_id VARCHAR,
	external_job_id VARCHAR NOT NULL,
	source VARCHAR NOT NULL,
	company VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	attempt_id VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	status_kind VARCHAR NOT NULL,
	reason VARCHAR NOT NULL,
	notes VARCHAR NOT NULL,
	follow_up VARCHAR NOT NULL,
	occurred_at DATETIME NOT NULL,
	legacy_date VARCHAR,
	provenance VARCHAR NOT NULL,
	file_sha256 VARCHAR,
	record_index INTEGER,
	unresolved VARCHAR,
	payload JSON NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (import_key),
	FOREIGN KEY(job_id) REFERENCES jobs (id)
);
CREATE TABLE application_packets (
	capacity_day VARCHAR,
	id VARCHAR NOT NULL,
	job_key VARCHAR NOT NULL,
	search_result_id INTEGER NOT NULL,
	canonical_job_id VARCHAR,
	fingerprint VARCHAR NOT NULL,
	scoring_fingerprint VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	status VARCHAR NOT NULL,
	score INTEGER NOT NULL,
	tier VARCHAR NOT NULL,
	company VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	ready_at DATETIME,
	cover_letter_acceptance VARCHAR NOT NULL,
	cover_letter VARCHAR NOT NULL,
	writing_fingerprints JSON NOT NULL,
	artifacts JSON NOT NULL,
	screening_answers JSON NOT NULL,
	referral_candidates JSON NOT NULL,
	referral_status VARCHAR NOT NULL,
	company_fact_ids JSON NOT NULL,
	content_flags JSON NOT NULL,
	verifier_status VARCHAR NOT NULL,
	lint_status VARCHAR NOT NULL,
	failure_reason VARCHAR,
	PRIMARY KEY (id),
	UNIQUE (job_key, version),
	CHECK (status IN ('building','packet_ready','generation_failed','research_incomplete','recovery_required')),
	CHECK (cover_letter_acceptance IN ('yes','no','unknown')),
	CHECK (verifier_status IN ('not_run','passed','failed')),
	CHECK (lint_status IN ('not_run','passed','failed')),
	CHECK (status != 'packet_ready' OR (verifier_status = 'passed' AND lint_status = 'passed' AND length(cover_letter) > 0 AND length(scoring_fingerprint) > 0 AND length(fingerprint) > 0)),
	FOREIGN KEY(search_result_id) REFERENCES search_results (id),
	FOREIGN KEY(canonical_job_id) REFERENCES jobs (id),
	UNIQUE (fingerprint)
);
CREATE TABLE company_facts (
	id VARCHAR NOT NULL,
	job_key VARCHAR NOT NULL,
	company VARCHAR NOT NULL,
	text VARCHAR NOT NULL,
	source_url VARCHAR NOT NULL,
	source_title VARCHAR NOT NULL,
	category VARCHAR NOT NULL,
	retrieved_at DATETIME NOT NULL,
	PRIMARY KEY (id)
);
CREATE TABLE job_identities (
	id INTEGER NOT NULL,
	job_id VARCHAR,
	source VARCHAR NOT NULL,
	external_id VARCHAR NOT NULL,
	posting_url VARCHAR,
	apply_url VARCHAR,
	first_seen DATETIME NOT NULL,
	last_seen DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (source, external_id),
	FOREIGN KEY(job_id) REFERENCES jobs (id)
);
CREATE TABLE jobs (
	id VARCHAR NOT NULL,
	company VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	location VARCHAR NOT NULL,
	posting_url VARCHAR NOT NULL,
	apply_url VARCHAR,
	first_seen DATETIME NOT NULL,
	last_seen DATETIME NOT NULL,
	application_status VARCHAR,
	application_status_kind VARCHAR,
	application_notes VARCHAR,
	application_follow_up VARCHAR,
	application_updated_at DATETIME,
	PRIMARY KEY (id)
);
CREATE TABLE llm_batches (
	id VARCHAR NOT NULL,
	provider_id VARCHAR,
	status VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	provider_created_at DATETIME,
	expires_at DATETIME,
	request_count INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (provider_id)
);
CREATE TABLE llm_calls (
	id VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	task VARCHAR NOT NULL,
	model VARCHAR NOT NULL,
	prompt_name VARCHAR NOT NULL,
	prompt_version VARCHAR NOT NULL,
	request_kind VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	input_tokens INTEGER NOT NULL,
	output_tokens INTEGER NOT NULL,
	cache_creation_input_tokens INTEGER NOT NULL,
	cache_read_input_tokens INTEGER NOT NULL,
	estimated_cost_usd VARCHAR NOT NULL,
	reserved_cost_usd VARCHAR NOT NULL,
	latency_ms INTEGER NOT NULL,
	error_type VARCHAR,
	error_message VARCHAR,
	provider_request_id VARCHAR,
	canonical_job_id VARCHAR,
	external_job_reference VARCHAR,
	operational_metadata JSON NOT NULL,
	PRIMARY KEY (id),
	CHECK (request_kind IN ('standard', 'batch')),
	CHECK (status IN ('reserved', 'succeeded', 'failed')),
	CHECK (input_tokens >= 0 AND output_tokens >= 0 AND cache_creation_input_tokens >= 0 AND cache_read_input_tokens >= 0)
);
CREATE TABLE scoring_work_items (
	id VARCHAR NOT NULL,
	fingerprint VARCHAR NOT NULL,
	source VARCHAR NOT NULL,
	external_id VARCHAR NOT NULL,
	canonical_job_id VARCHAR,
	search_result_id INTEGER,
	model VARCHAR NOT NULL,
	prompt_name VARCHAR NOT NULL,
	prompt_version VARCHAR NOT NULL,
	candidate_hash VARCHAR NOT NULL,
	reservation_cost_usd VARCHAR NOT NULL,
	state VARCHAR NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	priority_at DATETIME NOT NULL,
	attempt_count INTEGER NOT NULL,
	batch_id VARCHAR,
	custom_id VARCHAR,
	llm_call_id VARCHAR,
	failure VARCHAR,
	result JSON,
	PRIMARY KEY (id),
	CHECK (state IN ('pending','submitted','succeeded','retryable','failed','submission_unknown','standard_in_progress')),
	UNIQUE (fingerprint),
	FOREIGN KEY(canonical_job_id) REFERENCES jobs (id),
	FOREIGN KEY(search_result_id) REFERENCES search_results (id),
	FOREIGN KEY(batch_id) REFERENCES llm_batches (id),
	UNIQUE (custom_id),
	FOREIGN KEY(llm_call_id) REFERENCES llm_calls (id)
);
CREATE TABLE search_results (
	id INTEGER NOT NULL,
	run_id VARCHAR NOT NULL,
	legacy_key VARCHAR NOT NULL,
	identity_id INTEGER,
	unresolved VARCHAR,
	payload JSON NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (run_id, legacy_key),
	FOREIGN KEY(run_id) REFERENCES search_runs (id),
	FOREIGN KEY(identity_id) REFERENCES job_identities (id)
);
CREATE TABLE search_runs (
	id VARCHAR NOT NULL,
	generated_at VARCHAR,
	total INTEGER,
	new_count INTEGER,
	sources_queried INTEGER,
	payload JSON NOT NULL,
	PRIMARY KEY (id)
);
CREATE TABLE writing_work_items (
	fingerprint VARCHAR NOT NULL,
	packet_id VARCHAR,
	model VARCHAR NOT NULL,
	system_hash VARCHAR NOT NULL,
	user_hash VARCHAR NOT NULL,
	max_tokens INTEGER NOT NULL,
	prompt_name VARCHAR NOT NULL,
	prompt_version VARCHAR NOT NULL,
	failure_reason VARCHAR,
	updated_at DATETIME NOT NULL,
	task VARCHAR NOT NULL,
	state VARCHAR NOT NULL,
	output VARCHAR,
	output_hash VARCHAR,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (fingerprint),
	CHECK (state IN ('in_progress','succeeded','failed','recovery_required')),
	UNIQUE (packet_id, task),
	FOREIGN KEY(packet_id) REFERENCES application_packets (id)
);
CREATE INDEX ix_llm_calls_created_at ON llm_calls (created_at);
CREATE INDEX ix_job_identities_job_id ON job_identities (job_id);
CREATE INDEX ix_application_events_job_id ON application_events (job_id);
CREATE INDEX ix_scoring_work_items_search_result_id ON scoring_work_items (search_result_id);
CREATE INDEX ix_scoring_work_items_batch_id ON scoring_work_items (batch_id);
CREATE INDEX ix_scoring_work_items_state ON scoring_work_items (state);
CREATE INDEX ix_company_facts_job_key ON company_facts (job_key);
CREATE INDEX ix_application_packets_job_key ON application_packets (job_key);
CREATE INDEX ix_application_packets_capacity_day ON application_packets (capacity_day);
CREATE UNIQUE INDEX writing_packet_task ON writing_work_items(packet_id,task);
CREATE TRIGGER packet_capacity_day_immutable BEFORE UPDATE ON application_packets WHEN OLD.capacity_day IS NOT NULL AND (NEW.capacity_day IS NULL OR NEW.capacity_day != OLD.capacity_day) BEGIN SELECT RAISE(ABORT, 'capacity reservation is immutable'); END;
CREATE TRIGGER application_packets_status_insert BEFORE INSERT ON application_packets WHEN NEW.status IS NULL OR NEW.status NOT IN ('building','packet_ready','generation_failed','research_incomplete','recovery_required') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER application_packets_status_update BEFORE UPDATE ON application_packets WHEN NEW.status IS NULL OR NEW.status NOT IN ('building','packet_ready','generation_failed','research_incomplete','recovery_required') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER application_packets_cover_letter_acceptance_insert BEFORE INSERT ON application_packets WHEN NEW.cover_letter_acceptance IS NULL OR NEW.cover_letter_acceptance NOT IN ('yes','no','unknown') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER application_packets_cover_letter_acceptance_update BEFORE UPDATE ON application_packets WHEN NEW.cover_letter_acceptance IS NULL OR NEW.cover_letter_acceptance NOT IN ('yes','no','unknown') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER application_packets_verifier_status_insert BEFORE INSERT ON application_packets WHEN NEW.verifier_status IS NULL OR NEW.verifier_status NOT IN ('not_run','passed','failed') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER application_packets_verifier_status_update BEFORE UPDATE ON application_packets WHEN NEW.verifier_status IS NULL OR NEW.verifier_status NOT IN ('not_run','passed','failed') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER application_packets_lint_status_insert BEFORE INSERT ON application_packets WHEN NEW.lint_status IS NULL OR NEW.lint_status NOT IN ('not_run','passed','failed') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER application_packets_lint_status_update BEFORE UPDATE ON application_packets WHEN NEW.lint_status IS NULL OR NEW.lint_status NOT IN ('not_run','passed','failed') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER writing_work_items_state_insert BEFORE INSERT ON writing_work_items WHEN NEW.state IS NULL OR NEW.state NOT IN ('in_progress','succeeded','failed','recovery_required') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER writing_work_items_state_update BEFORE UPDATE ON writing_work_items WHEN NEW.state IS NULL OR NEW.state NOT IN ('in_progress','succeeded','failed','recovery_required') BEGIN SELECT RAISE(ABORT, 'invalid safety state'); END;
CREATE TRIGGER packet_ready_invariants_insert BEFORE INSERT ON application_packets WHEN NEW.status='packet_ready' AND (NEW.verifier_status!='passed' OR NEW.lint_status!='passed' OR length(NEW.cover_letter)=0 OR length(NEW.scoring_fingerprint)=0 OR length(NEW.fingerprint)=0) BEGIN SELECT RAISE(ABORT, 'invalid ready packet'); END;
CREATE TRIGGER packet_ready_invariants_update BEFORE UPDATE ON application_packets WHEN NEW.status='packet_ready' AND (NEW.verifier_status!='passed' OR NEW.lint_status!='passed' OR length(NEW.cover_letter)=0 OR length(NEW.scoring_fingerprint)=0 OR length(NEW.fingerprint)=0) BEGIN SELECT RAISE(ABORT, 'invalid ready packet'); END;
CREATE TRIGGER application_events_no_update BEFORE UPDATE ON application_events BEGIN SELECT RAISE(ABORT, 'application_events is append-only'); END;
CREATE TRIGGER application_events_no_delete BEFORE DELETE ON application_events BEGIN SELECT RAISE(ABORT, 'application_events is append-only'); END;
COMMIT;
PRAGMA user_version=6;
