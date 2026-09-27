CREATE TABLE `bco_config` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `bco_exchanges` (
	`id` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_bco_exchanges_expires` ON `bco_exchanges` (`expires`);--> statement-breakpoint
CREATE TABLE `bco_flows` (
	`id` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_bco_flows_expires` ON `bco_flows` (`expires`);--> statement-breakpoint
CREATE TABLE `bco_sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`expires` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_bco_sessions_expires` ON `bco_sessions` (`expires`);