/*
 Navicat Premium Dump SQL

 Source Server         : cookhero
 Source Server Type    : PostgreSQL
 Source Server Version : 160011 (160011)
 Source Host           : localhost:5432
 Source Catalog        : cookhero
 Source Schema         : public

 Target Server Type    : PostgreSQL
 Target Server Version : 160011 (160011)
 File Encoding         : 65001

 Date: 23/12/2025 23:30:45
*/

-- ============================================================================
-- Prerequisites for the schema created by these init scripts.
-- Required on a fresh database, otherwise the later scripts fail.
-- ============================================================================
-- uuid_generate_v4() used by conversations/messages/agent tables
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trigger function referenced by 02-conversations.sql and 07-agent_sessions.sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------
-- Table structure for users
-- ----------------------------
DROP TABLE IF EXISTS "public"."users";
CREATE TABLE "public"."users" (
  "id" uuid NOT NULL,
  "username" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "password_hash" text COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamp(6) NOT NULL,
  "occupation" varchar(100) COLLATE "pg_catalog"."default",
  "bio" text COLLATE "pg_catalog"."default",
  "profile" text COLLATE "pg_catalog"."default",
  "user_instruction" text COLLATE "pg_catalog"."default"
)
;
ALTER TABLE "public"."users" OWNER TO "cookhero";

-- ----------------------------
-- Indexes structure for table users
-- ----------------------------
CREATE UNIQUE INDEX "ix_users_username" ON "public"."users" USING btree (
  "username" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Uniques structure for table users
-- ----------------------------
ALTER TABLE "public"."users" ADD CONSTRAINT "users_username_key" UNIQUE ("username");

-- ----------------------------
-- Primary Key structure for table users
-- ----------------------------
ALTER TABLE "public"."users" ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");
