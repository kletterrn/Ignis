CREATE TABLE `records` (
	`kind` text NOT NULL,
	`id` text NOT NULL,
	`body` text NOT NULL,
	`acquired_at` text,
	`updated_at` text NOT NULL,
	PRIMARY KEY(`kind`, `id`)
);
--> statement-breakpoint
CREATE INDEX `records_acquired` ON `records` (`kind`,`acquired_at`);