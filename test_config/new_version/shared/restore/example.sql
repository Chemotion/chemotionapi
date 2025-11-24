--
-- PostgreSQL database dump
--

\restrict f22ngLBAWGP6AwBHkdbHHDUdnpvZi1kKTg3VqrpCoVgTuVnIOnNgVmEWJzhT6xf

-- Dumped from database version 16.9 (Debian 16.9-1.pgdg120+1)
-- Dumped by pg_dump version 16.10 (Ubuntu 16.10-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

--
-- Name: rdkit; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA rdkit;


ALTER SCHEMA rdkit OWNER TO postgres;

--
-- Name: hstore; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS hstore WITH SCHEMA public;


--
-- Name: EXTENSION hstore; Type: COMMENT; Schema: -; Owner:
--

COMMENT ON EXTENSION hstore IS 'data type for storing sets of (key, value) pairs';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner:
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner:
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: rdkit; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS rdkit WITH SCHEMA public;


--
-- Name: EXTENSION rdkit; Type: COMMENT; Schema: -; Owner:
--

COMMENT ON EXTENSION rdkit IS 'Cheminformatics functionality for PostgreSQL.';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner:
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: calculate_collection_space(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calculate_collection_space(collectionid integer) RETURNS bigint
    LANGUAGE plpgsql
    AS $_$
declare
    used_space bigint default 0;
    element_types text[] := array['Sample', 'Reaction', 'Wellplate', 'Screen', 'ResearchPlan'];
    element_table text;
    element_space bigint;
begin
    foreach element_table in array element_types loop
        execute format('select sum(calculate_element_space(id, $1)) from collections_%s where collection_id = $2', lower(element_table))
        into element_space
        using element_table, collectionId;
        used_space := used_space + coalesce(element_space, 0);
    end loop;
    return coalesce(used_space, 0);
end;
$_$;


ALTER FUNCTION public.calculate_collection_space(collectionid integer) OWNER TO postgres;

--
-- Name: calculate_dataset_space(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calculate_dataset_space(cid integer) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
declare
    used_space bigint default 0;
begin
    select sum((attachment_data->'metadata'->'size')::bigint) into used_space
    from attachments
    where attachable_type = 'Container' and attachable_id = cid
        and attachable_id in (select id from containers where container_type = 'dataset');
    return COALESCE(used_space,0);
end;$$;


ALTER FUNCTION public.calculate_dataset_space(cid integer) OWNER TO postgres;

--
-- Name: calculate_element_space(integer, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calculate_element_space(el_id integer, el_type text) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
declare
    used_space_attachments bigint default 0;
    used_space_datasets bigint default 0;
    used_space bigint default 0;
begin
    select sum((attachment_data->'metadata'->'size')::bigint) into used_space_attachments
    from attachments
    where attachable_type = el_type and attachable_id = el_id;
    used_space = COALESCE(used_space_attachments, 0);

    select sum(calculate_dataset_space(descendant_id)) into used_space_datasets
    from container_hierarchies where ancestor_id = (select id from containers where containable_id = el_id and containable_type = el_type);
    used_space = used_space + COALESCE(used_space_datasets, 0);

    return COALESCE(used_space, 0);
end;$$;


ALTER FUNCTION public.calculate_element_space(el_id integer, el_type text) OWNER TO postgres;

--
-- Name: calculate_used_space(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calculate_used_space(userid integer) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
declare
    used_space_samples bigint default 0;
    used_space_reactions bigint default 0;
    used_space_wellplates bigint default 0;
    used_space_screens bigint default 0;
    used_space_research_plans bigint default 0;
    used_space_reports bigint default 0;
    used_space_inbox bigint default 0;
    used_space bigint default 0;
begin
    select sum(calculate_element_space(s.sample_id, 'Sample')) into used_space_samples from (
        select distinct sample_id
        from collections_samples
        where collection_id in (select id from collections where user_id = userId)
    ) s;
    used_space = COALESCE(used_space_samples,0);

    select sum(calculate_element_space(r.reaction_id, 'Reaction')) into used_space_reactions from (
        select distinct reaction_id
        from collections_reactions
        where collection_id in (select id from collections where user_id = userId)
    ) r;
    used_space = used_space + COALESCE(used_space_reactions,0);

    select sum(calculate_element_space(wp.wellplate_id, 'Wellplate')) into used_space_wellplates from (
        select distinct wellplate_id
        from collections_wellplates
        where collection_id in (select id from collections where user_id = userId)
    ) wp;
    used_space = used_space + COALESCE(used_space_wellplates,0);

    select sum(calculate_element_space(wp.screen_id, 'Screen')) into used_space_screens from (
        select distinct screen_id
        from collections_screens
        where collection_id in (select id from collections where user_id = userId)
    ) wp;
    used_space = used_space + COALESCE(used_space_screens,0);

    select sum(calculate_element_space(rp.research_plan_id, 'ResearchPlan')) into used_space_research_plans from (
        select distinct research_plan_id
        from collections_research_plans
        where collection_id in (select id from collections where user_id = userId)
    ) rp;
    used_space = used_space + COALESCE(used_space_research_plans,0);

    select sum(calculate_element_space(id, 'Report')) into used_space_reports
    from reports
    where author_id = userId;
    used_space = used_space + COALESCE(used_space_reports,0);

    select sum((attachment_data->'metadata'->'size')::bigint) into used_space_inbox
    from attachments
    where attachable_type = 'Container'
        and attachable_id is null and created_for = userId;
        -- attachable_id is missing (why?), if this is a bug (and was fixed) change statement to
        -- and attachable_id = (select id from containers where containable_type='User' and containable_id=UserID);
    used_space = used_space + COALESCE(used_space_inbox,0);

    return COALESCE(used_space,0);
end;$$;


ALTER FUNCTION public.calculate_used_space(userid integer) OWNER TO postgres;

--
-- Name: collection_shared_names(integer, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.collection_shared_names(user_id integer, collection_id integer) RETURNS json
    LANGUAGE sql
    AS $_$
select array_to_json(array_agg(row_to_json(result))) from (
                                                              SELECT sync_collections_users.id, users.type,users.first_name || chr(32) || users.last_name as name,sync_collections_users.permission_level,
                                                                     sync_collections_users.reaction_detail_level,sync_collections_users.sample_detail_level,sync_collections_users.screen_detail_level,sync_collections_users.wellplate_detail_level
                                                              FROM sync_collections_users
                                                                       INNER JOIN users ON users.id = sync_collections_users.user_id AND users.deleted_at IS NULL
                                                              WHERE sync_collections_users.shared_by_id = $1 and sync_collections_users.collection_id = $2
                                                              group by  sync_collections_users.id,users.type,users.name_abbreviation,users.first_name,users.last_name,sync_collections_users.permission_level
                                                          ) as result
$_$;


ALTER FUNCTION public.collection_shared_names(user_id integer, collection_id integer) OWNER TO postgres;

--
-- Name: detail_level_for_sample(integer, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.detail_level_for_sample(in_user_id integer, in_sample_id integer) RETURNS TABLE(detail_level_sample integer, detail_level_wellplate integer)
    LANGUAGE plpgsql
    AS $$
declare
    i_detail_level_wellplate integer default 0;
    i_detail_level_sample integer default 0;
begin
    select max(all_cols.sample_detail_level), max(all_cols.wellplate_detail_level)
    into i_detail_level_sample, i_detail_level_wellplate
    from
        (
            select v_sams_cols.cols_sample_detail_level sample_detail_level, v_sams_cols.cols_wellplate_detail_level wellplate_detail_level
            from v_samples_collections v_sams_cols
            where v_sams_cols.sams_id = in_sample_id
              and v_sams_cols.cols_user_id in (select user_ids(in_user_id))
            union
            select sync_cols.sample_detail_level sample_detail_level, sync_cols.wellplate_detail_level wellplate_detail_level
            from sync_collections_users sync_cols
                     inner join collections cols on cols.id = sync_cols.collection_id and cols.deleted_at is null
            where sync_cols.collection_id in
                  (
                      select v_sams_cols.cols_id
                      from v_samples_collections v_sams_cols
                      where v_sams_cols.sams_id = in_sample_id
                  )
              and sync_cols.user_id in (select user_ids(in_user_id))
        ) all_cols;

    return query select coalesce(i_detail_level_sample,0) detail_level_sample, coalesce(i_detail_level_wellplate,0) detail_level_wellplate;
end;$$;


ALTER FUNCTION public.detail_level_for_sample(in_user_id integer, in_sample_id integer) OWNER TO postgres;

--
-- Name: generate_notifications(integer, integer, integer, integer[]); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.generate_notifications(in_channel_id integer, in_message_id integer, in_user_id integer, in_user_ids integer[]) RETURNS integer
    LANGUAGE plpgsql
    AS $$
declare
    i_channel_type int4;
    a_userids int4[];
    u int4;
begin
    select channel_type into i_channel_type
    from channels where id = in_channel_id;

    case i_channel_type
        when 9 then
            insert into notifications (message_id, user_id, created_at,updated_at)
                (select in_message_id, id, now(),now() from users where deleted_at is null and type='Person');
        when 5,8 then
            if (in_user_ids is not null) then
                a_userids = in_user_ids;
            end if;
            FOREACH u IN ARRAY a_userids
                loop
                    insert into notifications (message_id, user_id, created_at,updated_at)
                        (select distinct in_message_id, id, now(),now() from users where type='Person' and id in (select group_user_ids(u))
                                                                                     and not exists (select id from notifications where message_id = in_message_id and user_id = users.id));
                end loop;
        end case;
    return in_message_id;
end;$$;


ALTER FUNCTION public.generate_notifications(in_channel_id integer, in_message_id integer, in_user_id integer, in_user_ids integer[]) OWNER TO postgres;

--
-- Name: generate_users_matrix(integer[]); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.generate_users_matrix(in_user_ids integer[]) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
begin
    if in_user_ids is null then
        update users u set matrix = (
            select coalesce(sum(2^mx.id),0) from (
                                                     select distinct m1.* from matrices m1, users u1
                                                                                                left join users_groups ug1 on ug1.user_id = u1.id
                                                     where u.id = u1.id and ((m1.enabled = true) or ((u1.id = any(m1.include_ids)) or (u1.id = ug1.user_id and ug1.group_id = any(m1.include_ids))))
                                                     except
                                                     select distinct m2.* from matrices m2, users u2
                                                                                                left join users_groups ug2 on ug2.user_id = u2.id
                                                     where u.id = u2.id and ((u2.id = any(m2.exclude_ids)) or (u2.id = ug2.user_id and ug2.group_id = any(m2.exclude_ids)))
                                                 ) mx
        );
    else
        update users u set matrix = (
            select coalesce(sum(2^mx.id),0) from (
                                                     select distinct m1.* from matrices m1, users u1
                                                                                                left join users_groups ug1 on ug1.user_id = u1.id
                                                     where u.id = u1.id and ((m1.enabled = true) or ((u1.id = any(m1.include_ids)) or (u1.id = ug1.user_id and ug1.group_id = any(m1.include_ids))))
                                                     except
                                                     select distinct m2.* from matrices m2, users u2
                                                                                                left join users_groups ug2 on ug2.user_id = u2.id
                                                     where u.id = u2.id and ((u2.id = any(m2.exclude_ids)) or (u2.id = ug2.user_id and ug2.group_id = any(m2.exclude_ids)))
                                                 ) mx
        ) where ((in_user_ids) @> array[u.id]) or (u.id in (select ug3.user_id from users_groups ug3 where (in_user_ids) @> array[ug3.group_id]));
    end if;
    return true;
end
$$;


ALTER FUNCTION public.generate_users_matrix(in_user_ids integer[]) OWNER TO postgres;

--
-- Name: group_user_ids(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.group_user_ids(group_id integer) RETURNS TABLE(user_ids integer)
    LANGUAGE sql
    AS $_$
select id from users where type='Person' and id= $1
union
select user_id from users_groups where group_id = $1
$_$;


ALTER FUNCTION public.group_user_ids(group_id integer) OWNER TO postgres;

--
-- Name: jsonb_diff(jsonb, jsonb); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.jsonb_diff(old jsonb, new jsonb) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
DECLARE
  result jsonb := '{}'::jsonb;
  v RECORD;
  nested_diff jsonb;
  new_length int;
  old_length int;
BEGIN
  -- If old is NULL, return the new object as the full difference
  IF old IS NULL OR jsonb_typeof(old) = 'null' THEN
    RETURN new;
  END IF;

  -- If new is NULL, return an empty JSON
  IF new IS NULL OR jsonb_typeof(new) = 'null' THEN
    RETURN '{}'::jsonb;
  END IF;

  -- Handle top-level arrays
  IF jsonb_typeof(old) = 'array' AND jsonb_typeof(new) = 'array' THEN
    IF result = '{}' THEN
      result := '[]';
    END IF;

    -- If arrays are equal, return an empty JSON
    IF old = new THEN
      RETURN '[]'::jsonb;
    ELSE
      -- Return the new array as the diff
      -- Get array lengths
      new_length := JSONB_ARRAY_LENGTH(new);
      old_length := JSONB_ARRAY_LENGTH(old);

      -- Loop through the array using an index
      FOR i IN 0..new_length-1 LOOP
        IF i <= old_length THEN
          IF jsonb_typeof(new[i]) IN ('object','array') AND jsonb_typeof(old[i]) IN ('object','array') THEN
            nested_diff := jsonb_diff(old[i], new[i]);
            IF nested_diff <> '{}'::jsonb THEN
              result := result || nested_diff;
            END IF;
          ELSIF new[i] IS DISTINCT FROM old[i] THEN
            result := result || new[i];
          END IF;
        ELSE
          RETURN new[i];
        END IF;
      END LOOP;
      RETURN result;
    END IF;
  END IF;

  -- If types differ (object vs. array), return the full new value
  IF jsonb_typeof(old) <> jsonb_typeof(new) THEN
    RETURN new;
  END IF;

  -- Iterate through each key-value pair in new
  FOR v IN SELECT * FROM jsonb_each(new) LOOP
    -- If the key is an object in both old and new, recurse
    IF jsonb_typeof(old -> v.key) = 'object' AND jsonb_typeof(new -> v.key) = 'object' THEN
      nested_diff := jsonb_diff(old -> v.key, new -> v.key);
      IF nested_diff <> '{}'::jsonb THEN
        result := result || jsonb_build_object(v.key, nested_diff);
      END IF;
    -- If values are different, add to the result
    ELSIF (old -> v.key) IS DISTINCT FROM v.value THEN
      result := result || jsonb_build_object(v.key, v.value);
    END IF;
  END LOOP;

  -- Iterate through each key-value pair in old
  FOR v in SELECT * from jsonb_each(old) LOOP
    -- If value was deleted
    IF new -> v.key IS NULL AND jsonb_typeof(v.value) = 'object' THEN
      -- Append to result with value 'deleted'
      result := result || jsonb_build_object(v.key, 'deleted');
    END IF;
  END LOOP;

  RETURN result;
END;
$$;


ALTER FUNCTION public.jsonb_diff(old jsonb, new jsonb) OWNER TO postgres;

--
-- Name: lab_record_layers_changes(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.lab_record_layers_changes() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    BEGIN
        INSERT INTO layer_tracks (name, label, description, properties, identifier, created_by, created_at, updated_by, updated_at, deleted_by, deleted_at)
        VALUES (OLD.name, OLD.label, OLD.description, OLD.properties, OLD.identifier, OLD.created_by, OLD.created_at, OLD.updated_by, OLD.updated_at, OLD.deleted_by, OLD.deleted_at);
    EXCEPTION
        WHEN OTHERS THEN
            -- Ensure the main operation still completes successfully
    END;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.lab_record_layers_changes() OWNER TO postgres;

--
-- Name: labels_by_user_sample(integer, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.labels_by_user_sample(user_id integer, sample_id integer) RETURNS TABLE(labels text)
    LANGUAGE sql
    AS $_$
select string_agg(title::text, ', ') as labels from (select title from user_labels ul where ul.id in (
    select d.list
    from element_tags et, lateral (
        select value::integer as list
        from jsonb_array_elements_text(et.taggable_data  -> 'user_labels')
        ) d
    where et.taggable_id = $2 and et.taggable_type = 'Sample'
) and (ul.access_level = 1 or (ul.access_level = 0 and ul.user_id = $1)) order by title  ) uls
$_$;


ALTER FUNCTION public.labels_by_user_sample(user_id integer, sample_id integer) OWNER TO postgres;

--
-- Name: literatures_by_element(text, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.literatures_by_element(element_type text, element_id integer) RETURNS TABLE(literatures text)
    LANGUAGE sql
    AS $_$
select string_agg(l2.id::text, ',') as literatures from literals l , literatures l2
where l.literature_id = l2.id
  and l.element_type = $1 and l.element_id = $2
$_$;


ALTER FUNCTION public.literatures_by_element(element_type text, element_id integer) OWNER TO postgres;

--
-- Name: logidze_capture_exception(jsonb); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.logidze_capture_exception(error_data jsonb) RETURNS boolean
    LANGUAGE plpgsql
    AS $$
  -- version: 1
BEGIN
  -- Feel free to change this function to change Logidze behavior on exception.
  --
  -- Return `false` to raise exception or `true` to commit record changes.
  --
  -- `error_data` contains:
  --   - returned_sqlstate
  --   - message_text
  --   - pg_exception_detail
  --   - pg_exception_hint
  --   - pg_exception_context
  --   - schema_name
  --   - table_name
  -- Learn more about available keys:
  -- https://www.postgresql.org/docs/9.6/plpgsql-control-structures.html#PLPGSQL-EXCEPTION-DIAGNOSTICS-VALUES
  --

  return false;
END;
$$;


ALTER FUNCTION public.logidze_capture_exception(error_data jsonb) OWNER TO postgres;

--
-- Name: logidze_compact_history(jsonb, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.logidze_compact_history(log_data jsonb, cutoff integer DEFAULT 1) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
  -- version: 1
  DECLARE
    merged jsonb;
  BEGIN
    LOOP
      merged := jsonb_build_object(
        'ts',
        log_data#>'{h,1,ts}',
        'v',
        log_data#>'{h,1,v}',
        'c',
        (log_data#>'{h,0,c}') || (log_data#>'{h,1,c}')
      );

      IF (log_data#>'{h,1}' ? 'm') THEN
        merged := jsonb_set(merged, ARRAY['m'], log_data#>'{h,1,m}');
      END IF;

      log_data := jsonb_set(
        log_data,
        '{h}',
        jsonb_set(
          log_data->'h',
          '{1}',
          merged
        ) - 0
      );

      cutoff := cutoff - 1;

      EXIT WHEN cutoff <= 0;
    END LOOP;

    return log_data;
  END;
$$;


ALTER FUNCTION public.logidze_compact_history(log_data jsonb, cutoff integer) OWNER TO postgres;

--
-- Name: logidze_create_trigger_on_table(text, text, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.logidze_create_trigger_on_table(table_name text, trigger_name text, timestamp_column text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- CREATE TRIGGER logidze_on_{table_name}
    -- Parameters: history_size_limit (integer), timestamp_column (text), filtered_columns (text[]),
    -- include_columns (boolean), debounce_time_ms (integer)
    EXECUTE format( '
        CREATE TRIGGER %I
        BEFORE UPDATE OR INSERT ON %I
        FOR EACH ROW
        WHEN (coalesce(current_setting(''logidze.disabled'', true), '''') <> ''on'')
        EXECUTE PROCEDURE logidze_logger(null, %L)', trigger_name, table_name, timestamp_column);
END;
$$;


ALTER FUNCTION public.logidze_create_trigger_on_table(table_name text, trigger_name text, timestamp_column text) OWNER TO postgres;

--
-- Name: logidze_filter_keys(jsonb, text[], boolean); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.logidze_filter_keys(obj jsonb, keys text[], include_columns boolean DEFAULT false) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
  -- version: 1
  DECLARE
    res jsonb;
    key text;
  BEGIN
    res := '{}';

    IF include_columns THEN
      FOREACH key IN ARRAY keys
      LOOP
        IF obj ? key THEN
          res = jsonb_insert(res, ARRAY[key], obj->key);
        END IF;
      END LOOP;
    ELSE
      res = obj;
      FOREACH key IN ARRAY keys
      LOOP
        res = res - key;
      END LOOP;
    END IF;

    RETURN res;
  END;
$$;


ALTER FUNCTION public.logidze_filter_keys(obj jsonb, keys text[], include_columns boolean) OWNER TO postgres;

--
-- Name: logidze_logger(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.logidze_logger() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
  -- version: 3
  DECLARE
    changes jsonb;
    version jsonb;
    snapshot jsonb;
    new_v integer;
    size integer;
    history_limit integer;
    debounce_time integer;
    current_version integer;
    k text;
    iterator integer;
    item record;
    columns text[];
    include_columns boolean;
    ts timestamp with time zone;
    ts_column text;
    err_sqlstate text;
    err_message text;
    err_detail text;
    err_hint text;
    err_context text;
    err_table_name text;
    err_schema_name text;
    err_jsonb jsonb;
    err_captured boolean;
  BEGIN
    ts_column := NULLIF(TG_ARGV[1], 'null');
    columns := NULLIF(TG_ARGV[2], 'null');
    include_columns := NULLIF(TG_ARGV[3], 'null');

    IF TG_OP = 'INSERT' THEN
      IF columns IS NOT NULL THEN
        snapshot = logidze_snapshot(to_jsonb(NEW.*), ts_column, columns, include_columns);
      ELSE
        snapshot = logidze_snapshot(to_jsonb(NEW.*), ts_column);
      END IF;

      IF snapshot#>>'{h, -1, c}' != '{}' THEN
        NEW.log_data := snapshot;
      END IF;

    ELSIF TG_OP = 'UPDATE' THEN

      IF OLD.log_data is NULL OR OLD.log_data = '{}'::jsonb THEN
        IF columns IS NOT NULL THEN
          snapshot = logidze_snapshot(to_jsonb(NEW.*), ts_column, columns, include_columns);
        ELSE
          snapshot = logidze_snapshot(to_jsonb(NEW.*), ts_column);
        END IF;

        IF snapshot#>>'{h, -1, c}' != '{}' THEN
          NEW.log_data := snapshot;
        END IF;
        RETURN NEW;
      END IF;

      history_limit := NULLIF(TG_ARGV[0], 'null');
      debounce_time := NULLIF(TG_ARGV[4], 'null');

      current_version := (NEW.log_data->>'v')::int;

      IF ts_column IS NULL THEN
        ts := statement_timestamp();
      ELSE
        ts := (to_jsonb(NEW.*)->>ts_column)::timestamp with time zone;
        IF ts IS NULL OR ts = (to_jsonb(OLD.*)->>ts_column)::timestamp with time zone THEN
          ts := statement_timestamp();
        END IF;
      END IF;

      IF NEW = OLD THEN
        RETURN NEW;
      END IF;

      IF current_version < (NEW.log_data#>>'{h,-1,v}')::int THEN
        iterator := 0;
        FOR item in SELECT * FROM jsonb_array_elements(NEW.log_data->'h')
        LOOP
          IF (item.value->>'v')::int > current_version THEN
            NEW.log_data := jsonb_set(
              NEW.log_data,
              '{h}',
              (NEW.log_data->'h') - iterator
            );
          END IF;
          iterator := iterator + 1;
        END LOOP;
      END IF;

      changes := '{}';

      IF (coalesce(current_setting('logidze.full_snapshot', true), '') = 'on') THEN
        BEGIN
          changes = hstore_to_jsonb_loose(hstore(NEW.*));
        EXCEPTION
          WHEN NUMERIC_VALUE_OUT_OF_RANGE THEN
            changes = row_to_json(NEW.*)::jsonb;
            FOR k IN (SELECT key FROM jsonb_each(changes))
            LOOP
              IF jsonb_typeof(changes->k) = 'object' THEN
                changes = jsonb_set(changes, ARRAY[k], to_jsonb(changes->>k));
              END IF;
            END LOOP;
        END;
      ELSE
        WITH
          new_kv AS (
            SELECT key, value FROM jsonb_each(row_to_json(NEW)::jsonb)
          ),
          old_kv AS (
            SELECT key, value FROM jsonb_each(row_to_json(OLD)::jsonb)
          ),
          all_keys AS (
            SELECT key FROM new_kv
            UNION
            SELECT key FROM old_kv
          )
        SELECT COALESCE(jsonb_object_agg(key, value), '{}'::jsonb)
        INTO changes
        FROM (
          SELECT
            k.key,
            CASE
              WHEN n.value IS NULL THEN
                -- key missing in NEW → mark deleted
                to_jsonb('deleted'::text)
              WHEN o.value IS NULL THEN
                -- key missing in OLD → addition
                n.value
              WHEN n.value <> o.value THEN
                -- key present in both but different → changed
                n.value
              ELSE
                -- identical → exclude by returning NULL (will be filtered out)
                NULL
            END AS value
          FROM all_keys k
          LEFT JOIN new_kv n ON k.key = n.key
          LEFT JOIN old_kv o ON k.key = o.key
        ) t
        WHERE value IS NOT NULL;

        FOR k IN SELECT key FROM jsonb_each(changes)
          LOOP
            IF jsonb_typeof(changes->k) = 'object' THEN
              changes := jsonb_set(
                changes,
                ARRAY[k],
                jsonb_diff(
                  row_to_json(OLD)::jsonb -> k,
                  row_to_json(NEW)::jsonb -> k
                )
              );
            END IF;
          END LOOP;
      END IF;

      changes = changes - 'log_data';

      IF columns IS NOT NULL THEN
        changes = logidze_filter_keys(changes, columns, include_columns);
      END IF;

      IF changes = '{}' THEN
        RETURN NEW;
      END IF;

      new_v := (NEW.log_data#>>'{h,-1,v}')::int + 1;

      size := jsonb_array_length(NEW.log_data->'h');
      version := logidze_version(new_v, changes, ts);

      IF (
        debounce_time IS NOT NULL AND
        (version->>'ts')::bigint - (NEW.log_data#>'{h,-1,ts}')::text::bigint <= debounce_time
      ) THEN
        -- merge new version with the previous one
        new_v := (NEW.log_data#>>'{h,-1,v}')::int;
        version := logidze_version(new_v, (NEW.log_data#>'{h,-1,c}')::jsonb || changes, ts);
        -- remove the previous version from log
        NEW.log_data := jsonb_set(
          NEW.log_data,
          '{h}',
          (NEW.log_data->'h') - (size - 1)
        );
      END IF;

      NEW.log_data := jsonb_set(
        NEW.log_data,
        ARRAY['h', size::text],
        version,
        true
      );

      NEW.log_data := jsonb_set(
        NEW.log_data,
        '{v}',
        to_jsonb(new_v)
      );

      IF history_limit IS NOT NULL AND history_limit <= size THEN
        NEW.log_data := logidze_compact_history(NEW.log_data, size - history_limit + 1);
      END IF;
    END IF;

    return NEW;
  EXCEPTION
    WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS err_sqlstate = RETURNED_SQLSTATE,
                              err_message = MESSAGE_TEXT,
                              err_detail = PG_EXCEPTION_DETAIL,
                              err_hint = PG_EXCEPTION_HINT,
                              err_context = PG_EXCEPTION_CONTEXT,
                              err_schema_name = SCHEMA_NAME,
                              err_table_name = TABLE_NAME;
      err_jsonb := jsonb_build_object(
        'returned_sqlstate', err_sqlstate,
        'message_text', err_message,
        'pg_exception_detail', err_detail,
        'pg_exception_hint', err_hint,
        'pg_exception_context', err_context,
        'schema_name', err_schema_name,
        'table_name', err_table_name
      );
      err_captured = logidze_capture_exception(err_jsonb);
      IF err_captured THEN
        return NEW;
      ELSE
        RAISE;
      END IF;
  END;
$$;


ALTER FUNCTION public.logidze_logger() OWNER TO postgres;

--
-- Name: logidze_snapshot(jsonb, text, text[], boolean); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.logidze_snapshot(item jsonb, ts_column text DEFAULT NULL::text, columns text[] DEFAULT NULL::text[], include_columns boolean DEFAULT false) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
  -- version: 3
  DECLARE
    ts timestamp with time zone;
    k text;
  BEGIN
    item = item - 'log_data';
    IF ts_column IS NULL THEN
      ts := statement_timestamp();
    ELSE
      ts := coalesce((item->>ts_column)::timestamp with time zone, statement_timestamp());
    END IF;

    IF columns IS NOT NULL THEN
      item := logidze_filter_keys(item, columns, include_columns);
    END IF;

    FOR k IN (SELECT key FROM jsonb_each(item))
    LOOP
      IF jsonb_typeof(item->k) = 'object' THEN
         item := jsonb_set(item, ARRAY[k], to_jsonb(item->>k));
      END IF;
    END LOOP;

    return json_build_object(
      'v', 1,
      'h', jsonb_build_array(
              logidze_version(1, item, ts)
            )
      );
  END;
$$;


ALTER FUNCTION public.logidze_snapshot(item jsonb, ts_column text, columns text[], include_columns boolean) OWNER TO postgres;

--
-- Name: logidze_version(bigint, jsonb, timestamp with time zone); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.logidze_version(v bigint, data jsonb, ts timestamp with time zone) RETURNS jsonb
    LANGUAGE plpgsql
    AS $$
  -- version: 2
  DECLARE
    buf jsonb;
  BEGIN
    data = data - 'log_data';
    buf := jsonb_build_object(
              'ts',
              (extract(epoch from ts) * 1000)::bigint,
              'v',
              v,
              'c',
              data
              );
    IF coalesce(current_setting('logidze.meta', true), '') <> '' THEN
      buf := jsonb_insert(buf, '{m}', current_setting('logidze.meta')::jsonb);
    END IF;
    RETURN buf;
  END;
$$;


ALTER FUNCTION public.logidze_version(v bigint, data jsonb, ts timestamp with time zone) OWNER TO postgres;

--
-- Name: set_samples_mol_rdkit(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.set_samples_mol_rdkit() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
	if (TG_OP='INSERT') then
		insert into rdkit.mols values (new.id, mol_from_ctab(encode(new.molfile, 'escape')::cstring));
	end if;
	if (TG_OP='UPDATE') then
		if new.MOLFILE <> old.MOLFILE then
			update rdkit.mols set m = mol_from_ctab(encode(new.molfile, 'escape')::cstring) where id = new.id;
		end if;
	end if;
	return new;
end
$$;


ALTER FUNCTION public.set_samples_mol_rdkit() OWNER TO postgres;

--
-- Name: shared_user_as_json(integer, integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.shared_user_as_json(in_user_id integer, in_current_user_id integer) RETURNS json
    LANGUAGE plpgsql
    AS $_$
begin
    if (in_user_id = in_current_user_id) then
        return null;
    else
        return (select row_to_json(result) from (
                                                    select users.id, users.name_abbreviation as initials ,users.type,users.first_name || chr(32) || users.last_name as name
                                                    from users where id = $1
                                                ) as result);
    end if;
end;
$_$;


ALTER FUNCTION public.shared_user_as_json(in_user_id integer, in_current_user_id integer) OWNER TO postgres;

--
-- Name: update_users_matrix(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_users_matrix() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
    if (TG_OP='INSERT') then
        PERFORM generate_users_matrix(null);
    end if;

    if (TG_OP='UPDATE') then
        if new.enabled <> old.enabled or new.deleted_at <> new.deleted_at then
            PERFORM generate_users_matrix(null);
        elsif new.include_ids <> old.include_ids then
            PERFORM generate_users_matrix(new.include_ids || old.include_ids);
        elsif new.exclude_ids <> old.exclude_ids then
            PERFORM generate_users_matrix(new.exclude_ids || old.exclude_ids);
        end if;
    end if;
    return new;
end
$$;


ALTER FUNCTION public.update_users_matrix() OWNER TO postgres;

--
-- Name: user_as_json(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.user_as_json(user_id integer) RETURNS json
    LANGUAGE sql
    AS $_$
select row_to_json(result) from (
                                    select users.id, users.name_abbreviation as initials ,users.type,users.first_name || chr(32) || users.last_name as name
                                    from users where id = $1
                                ) as result
$_$;


ALTER FUNCTION public.user_as_json(user_id integer) OWNER TO postgres;

--
-- Name: user_ids(integer); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.user_ids(user_id integer) RETURNS TABLE(user_ids integer)
    LANGUAGE sql
    AS $_$
select $1 as id
union
(select users.id from users inner join users_groups ON users.id = users_groups.group_id WHERE users.deleted_at IS null
                                                                                          and users.type in ('Group') and users_groups.user_id = $1)
$_$;


ALTER FUNCTION public.user_ids(user_id integer) OWNER TO postgres;

--
-- Name: user_instrument(integer, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.user_instrument(user_id integer, sc text) RETURNS TABLE(instrument text)
    LANGUAGE sql
    AS $_$
select distinct extended_metadata -> 'instrument' as instrument from containers c
where c.container_type='dataset' and c.id in
                                     (select ch.descendant_id from containers sc,container_hierarchies ch, samples s, users u
                                      where sc.containable_type in ('Sample','Reaction') and ch.ancestor_id=sc.id and sc.containable_id=s.id
                                        and s.created_by = u.id and u.id = $1 and ch.generations=3 group by descendant_id)
  and upper(extended_metadata -> 'instrument') like upper($2 || '%')
order by extended_metadata -> 'instrument' limit 10
$_$;


ALTER FUNCTION public.user_instrument(user_id integer, sc text) OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: affiliations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.affiliations (
    id integer NOT NULL,
    company character varying,
    country character varying,
    organization character varying,
    department character varying,
    "group" character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    "from" date,
    "to" date,
    domain character varying,
    cat character varying
);


ALTER TABLE public.affiliations OWNER TO postgres;

--
-- Name: affiliations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.affiliations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.affiliations_id_seq OWNER TO postgres;

--
-- Name: affiliations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.affiliations_id_seq OWNED BY public.affiliations.id;


--
-- Name: analyses_experiments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.analyses_experiments (
    id integer NOT NULL,
    sample_id integer,
    holder_id integer,
    status character varying,
    devices_analysis_id integer NOT NULL,
    devices_sample_id integer NOT NULL,
    sample_analysis_id character varying NOT NULL,
    solvent character varying,
    experiment character varying,
    priority boolean,
    on_day boolean,
    number_of_scans integer,
    sweep_width integer,
    "time" character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.analyses_experiments OWNER TO postgres;

--
-- Name: analyses_experiments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.analyses_experiments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.analyses_experiments_id_seq OWNER TO postgres;

--
-- Name: analyses_experiments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.analyses_experiments_id_seq OWNED BY public.analyses_experiments.id;


--
-- Name: ar_internal_metadata; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ar_internal_metadata (
    key character varying NOT NULL,
    value character varying,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL
);


ALTER TABLE public.ar_internal_metadata OWNER TO postgres;

--
-- Name: attachments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.attachments (
    id integer NOT NULL,
    attachable_id integer,
    filename character varying,
    identifier uuid DEFAULT public.uuid_generate_v4(),
    checksum character varying,
    storage character varying(20) DEFAULT 'tmp'::character varying,
    created_by integer NOT NULL,
    created_for integer,
    version character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    content_type character varying,
    bucket character varying,
    key character varying(500),
    thumb boolean DEFAULT false,
    folder character varying,
    attachable_type character varying,
    aasm_state character varying,
    filesize bigint,
    attachment_data jsonb,
    con_state integer,
    deleted_at timestamp without time zone,
    log_data jsonb,
    created_by_type character varying
);


ALTER TABLE public.attachments OWNER TO postgres;

--
-- Name: attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.attachments_id_seq OWNER TO postgres;

--
-- Name: attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.attachments_id_seq OWNED BY public.attachments.id;


--
-- Name: authentication_keys; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.authentication_keys (
    id integer NOT NULL,
    token character varying NOT NULL,
    user_id integer,
    ip inet,
    role character varying,
    fqdn character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE public.authentication_keys OWNER TO postgres;

--
-- Name: authentication_keys_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.authentication_keys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.authentication_keys_id_seq OWNER TO postgres;

--
-- Name: authentication_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.authentication_keys_id_seq OWNED BY public.authentication_keys.id;


--
-- Name: calendar_entries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.calendar_entries (
    id bigint NOT NULL,
    title character varying,
    description character varying,
    start_time timestamp without time zone,
    end_time timestamp without time zone,
    kind character varying,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    eventable_type character varying,
    eventable_id bigint
);


ALTER TABLE public.calendar_entries OWNER TO postgres;

--
-- Name: calendar_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.calendar_entries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.calendar_entries_id_seq OWNER TO postgres;

--
-- Name: calendar_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.calendar_entries_id_seq OWNED BY public.calendar_entries.id;


--
-- Name: calendar_entry_notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.calendar_entry_notifications (
    id bigint NOT NULL,
    user_id bigint,
    calendar_entry_id bigint,
    status integer DEFAULT 0,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL
);


ALTER TABLE public.calendar_entry_notifications OWNER TO postgres;

--
-- Name: calendar_entry_notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.calendar_entry_notifications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.calendar_entry_notifications_id_seq OWNER TO postgres;

--
-- Name: calendar_entry_notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.calendar_entry_notifications_id_seq OWNED BY public.calendar_entry_notifications.id;


--
-- Name: cellline_materials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cellline_materials (
    id bigint NOT NULL,
    name character varying,
    source character varying,
    cell_type character varying,
    organism jsonb,
    tissue jsonb,
    disease jsonb,
    growth_medium character varying,
    biosafety_level character varying,
    variant character varying,
    mutation character varying,
    optimal_growth_temp double precision,
    cryo_pres_medium character varying,
    gender character varying,
    description character varying,
    deleted_at timestamp without time zone,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL,
    created_by integer
);


ALTER TABLE public.cellline_materials OWNER TO postgres;

--
-- Name: cellline_materials_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cellline_materials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cellline_materials_id_seq OWNER TO postgres;

--
-- Name: cellline_materials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cellline_materials_id_seq OWNED BY public.cellline_materials.id;


--
-- Name: cellline_samples; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cellline_samples (
    id bigint NOT NULL,
    cellline_material_id bigint,
    cellline_sample_id bigint,
    amount bigint,
    unit character varying,
    passage integer,
    contamination character varying,
    name character varying,
    description character varying,
    user_id bigint,
    deleted_at timestamp without time zone,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL,
    short_label character varying,
    ancestry character varying
);


ALTER TABLE public.cellline_samples OWNER TO postgres;

--
-- Name: cellline_samples_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cellline_samples_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cellline_samples_id_seq OWNER TO postgres;

--
-- Name: cellline_samples_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cellline_samples_id_seq OWNED BY public.cellline_samples.id;


--
-- Name: channels; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.channels (
    id integer NOT NULL,
    subject character varying,
    msg_template jsonb,
    channel_type integer DEFAULT 0,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.channels OWNER TO postgres;

--
-- Name: channels_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.channels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.channels_id_seq OWNER TO postgres;

--
-- Name: channels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.channels_id_seq OWNED BY public.channels.id;


--
-- Name: chemicals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chemicals (
    id bigint NOT NULL,
    sample_id integer,
    cas text,
    chemical_data jsonb,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    log_data jsonb
);


ALTER TABLE public.chemicals OWNER TO postgres;

--
-- Name: chemicals_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chemicals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chemicals_id_seq OWNER TO postgres;

--
-- Name: chemicals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chemicals_id_seq OWNED BY public.chemicals.id;


--
-- Name: code_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.code_logs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    source character varying,
    source_id integer,
    value character varying(40),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.code_logs OWNER TO postgres;

--
-- Name: collections; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections (
    id integer NOT NULL,
    user_id integer NOT NULL,
    ancestry character varying,
    label text NOT NULL,
    shared_by_id integer,
    is_shared boolean DEFAULT false,
    permission_level integer DEFAULT 0,
    sample_detail_level integer DEFAULT 10,
    reaction_detail_level integer DEFAULT 10,
    wellplate_detail_level integer DEFAULT 10,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    "position" integer,
    screen_detail_level integer DEFAULT 10,
    is_locked boolean DEFAULT false,
    deleted_at timestamp without time zone,
    is_synchronized boolean DEFAULT false NOT NULL,
    researchplan_detail_level integer DEFAULT 10,
    element_detail_level integer DEFAULT 10,
    tabs_segment jsonb DEFAULT '{}'::jsonb,
    celllinesample_detail_level integer DEFAULT 10,
    inventory_id bigint,
    devicedescription_detail_level integer DEFAULT 10
);


ALTER TABLE public.collections OWNER TO postgres;

--
-- Name: collections_celllines; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_celllines (
    id bigint NOT NULL,
    collection_id integer,
    cellline_sample_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_celllines OWNER TO postgres;

--
-- Name: collections_celllines_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_celllines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_celllines_id_seq OWNER TO postgres;

--
-- Name: collections_celllines_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_celllines_id_seq OWNED BY public.collections_celllines.id;


--
-- Name: collections_device_descriptions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_device_descriptions (
    id bigint NOT NULL,
    collection_id integer,
    device_description_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_device_descriptions OWNER TO postgres;

--
-- Name: collections_device_descriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_device_descriptions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_device_descriptions_id_seq OWNER TO postgres;

--
-- Name: collections_device_descriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_device_descriptions_id_seq OWNED BY public.collections_device_descriptions.id;


--
-- Name: collections_elements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_elements (
    id integer NOT NULL,
    collection_id integer,
    element_id integer,
    element_type character varying,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_elements OWNER TO postgres;

--
-- Name: collections_elements_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_elements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_elements_id_seq OWNER TO postgres;

--
-- Name: collections_elements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_elements_id_seq OWNED BY public.collections_elements.id;


--
-- Name: collections_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_id_seq OWNER TO postgres;

--
-- Name: collections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_id_seq OWNED BY public.collections.id;


--
-- Name: collections_reactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_reactions (
    id integer NOT NULL,
    collection_id integer,
    reaction_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_reactions OWNER TO postgres;

--
-- Name: collections_reactions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_reactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_reactions_id_seq OWNER TO postgres;

--
-- Name: collections_reactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_reactions_id_seq OWNED BY public.collections_reactions.id;


--
-- Name: collections_research_plans; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_research_plans (
    id integer NOT NULL,
    collection_id integer,
    research_plan_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_research_plans OWNER TO postgres;

--
-- Name: collections_research_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_research_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_research_plans_id_seq OWNER TO postgres;

--
-- Name: collections_research_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_research_plans_id_seq OWNED BY public.collections_research_plans.id;


--
-- Name: collections_samples; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_samples (
    id integer NOT NULL,
    collection_id integer,
    sample_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_samples OWNER TO postgres;

--
-- Name: collections_samples_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_samples_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_samples_id_seq OWNER TO postgres;

--
-- Name: collections_samples_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_samples_id_seq OWNED BY public.collections_samples.id;


--
-- Name: collections_screens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_screens (
    id integer NOT NULL,
    collection_id integer,
    screen_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_screens OWNER TO postgres;

--
-- Name: collections_screens_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_screens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_screens_id_seq OWNER TO postgres;

--
-- Name: collections_screens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_screens_id_seq OWNED BY public.collections_screens.id;


--
-- Name: collections_vessels; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_vessels (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    collection_id bigint,
    vessel_id uuid,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_vessels OWNER TO postgres;

--
-- Name: collections_wellplates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collections_wellplates (
    id integer NOT NULL,
    collection_id integer,
    wellplate_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.collections_wellplates OWNER TO postgres;

--
-- Name: collections_wellplates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collections_wellplates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collections_wellplates_id_seq OWNER TO postgres;

--
-- Name: collections_wellplates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collections_wellplates_id_seq OWNED BY public.collections_wellplates.id;


--
-- Name: collector_errors; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.collector_errors (
    id integer NOT NULL,
    error_code character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.collector_errors OWNER TO postgres;

--
-- Name: collector_errors_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.collector_errors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.collector_errors_id_seq OWNER TO postgres;

--
-- Name: collector_errors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.collector_errors_id_seq OWNED BY public.collector_errors.id;


--
-- Name: comments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.comments (
    id bigint NOT NULL,
    content character varying,
    created_by integer NOT NULL,
    section character varying,
    status character varying DEFAULT 'Pending'::character varying,
    submitter character varying,
    resolver_name character varying,
    commentable_id integer,
    commentable_type character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.comments OWNER TO postgres;

--
-- Name: comments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.comments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.comments_id_seq OWNER TO postgres;

--
-- Name: comments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.comments_id_seq OWNED BY public.comments.id;


--
-- Name: computed_props; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.computed_props (
    id integer NOT NULL,
    molecule_id integer,
    max_potential double precision DEFAULT 0.0,
    min_potential double precision DEFAULT 0.0,
    mean_potential double precision DEFAULT 0.0,
    lumo double precision DEFAULT 0.0,
    homo double precision DEFAULT 0.0,
    ip double precision DEFAULT 0.0,
    ea double precision DEFAULT 0.0,
    dipol_debye double precision DEFAULT 0.0,
    status integer DEFAULT 0,
    data jsonb,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    mean_abs_potential double precision DEFAULT 0.0,
    creator integer DEFAULT 0,
    sample_id integer DEFAULT 0,
    tddft jsonb DEFAULT '{}'::jsonb,
    task_id character varying,
    deleted_at timestamp without time zone
);


ALTER TABLE public.computed_props OWNER TO postgres;

--
-- Name: computed_props_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.computed_props_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.computed_props_id_seq OWNER TO postgres;

--
-- Name: computed_props_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.computed_props_id_seq OWNED BY public.computed_props.id;


--
-- Name: container_hierarchies; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.container_hierarchies (
    ancestor_id integer NOT NULL,
    descendant_id integer NOT NULL,
    generations integer NOT NULL
);


ALTER TABLE public.container_hierarchies OWNER TO postgres;

--
-- Name: containers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.containers (
    id integer NOT NULL,
    ancestry character varying,
    containable_id integer,
    containable_type character varying,
    name character varying,
    container_type character varying,
    description text,
    extended_metadata public.hstore DEFAULT ''::public.hstore,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    parent_id integer,
    plain_text_content text,
    deleted_at timestamp without time zone,
    log_data jsonb
);


ALTER TABLE public.containers OWNER TO postgres;

--
-- Name: containers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.containers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.containers_id_seq OWNER TO postgres;

--
-- Name: containers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.containers_id_seq OWNED BY public.containers.id;


--
-- Name: dataset_klasses; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.dataset_klasses (
    id integer NOT NULL,
    ols_term_id character varying NOT NULL,
    label character varying NOT NULL,
    "desc" character varying,
    properties_template jsonb DEFAULT '{"layers": {}, "select_options": {}}'::jsonb NOT NULL,
    is_active boolean DEFAULT false NOT NULL,
    place integer DEFAULT 100 NOT NULL,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    uuid character varying,
    properties_release jsonb DEFAULT '{}'::jsonb,
    released_at timestamp without time zone,
    identifier character varying,
    sync_time timestamp without time zone,
    updated_by integer,
    released_by integer,
    sync_by integer,
    admin_ids jsonb DEFAULT '{}'::jsonb,
    user_ids jsonb DEFAULT '{}'::jsonb,
    version character varying
);


ALTER TABLE public.dataset_klasses OWNER TO postgres;

--
-- Name: dataset_klasses_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.dataset_klasses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.dataset_klasses_id_seq OWNER TO postgres;

--
-- Name: dataset_klasses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.dataset_klasses_id_seq OWNED BY public.dataset_klasses.id;


--
-- Name: dataset_klasses_revisions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.dataset_klasses_revisions (
    id integer NOT NULL,
    dataset_klass_id integer,
    uuid character varying,
    properties_release jsonb DEFAULT '{}'::jsonb,
    released_at timestamp without time zone,
    released_by integer,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    version character varying
);


ALTER TABLE public.dataset_klasses_revisions OWNER TO postgres;

--
-- Name: dataset_klasses_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.dataset_klasses_revisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.dataset_klasses_revisions_id_seq OWNER TO postgres;

--
-- Name: dataset_klasses_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.dataset_klasses_revisions_id_seq OWNED BY public.dataset_klasses_revisions.id;


--
-- Name: datasets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.datasets (
    id integer NOT NULL,
    dataset_klass_id integer,
    element_type character varying,
    element_id integer,
    properties jsonb,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone,
    uuid character varying,
    klass_uuid character varying,
    deleted_at timestamp without time zone,
    properties_release jsonb
);


ALTER TABLE public.datasets OWNER TO postgres;

--
-- Name: datasets_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.datasets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.datasets_id_seq OWNER TO postgres;

--
-- Name: datasets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.datasets_id_seq OWNED BY public.datasets.id;


--
-- Name: datasets_revisions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.datasets_revisions (
    id integer NOT NULL,
    dataset_id integer,
    uuid character varying,
    klass_uuid character varying,
    properties jsonb DEFAULT '{}'::jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    properties_release jsonb
);


ALTER TABLE public.datasets_revisions OWNER TO postgres;

--
-- Name: datasets_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.datasets_revisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.datasets_revisions_id_seq OWNER TO postgres;

--
-- Name: datasets_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.datasets_revisions_id_seq OWNED BY public.datasets_revisions.id;


--
-- Name: delayed_jobs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.delayed_jobs (
    id integer NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    handler text NOT NULL,
    last_error text,
    run_at timestamp without time zone,
    locked_at timestamp without time zone,
    failed_at timestamp without time zone,
    locked_by character varying,
    queue character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    cron character varying
);


ALTER TABLE public.delayed_jobs OWNER TO postgres;

--
-- Name: delayed_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.delayed_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.delayed_jobs_id_seq OWNER TO postgres;

--
-- Name: delayed_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.delayed_jobs_id_seq OWNED BY public.delayed_jobs.id;


--
-- Name: device_descriptions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.device_descriptions (
    id bigint NOT NULL,
    access_comments character varying,
    access_options character varying,
    ancestry character varying,
    application_name character varying,
    application_version character varying,
    building character varying,
    contact_for_maintenance jsonb,
    consumables_needed_for_maintenance jsonb,
    created_by integer,
    deleted_at timestamp without time zone,
    description text,
    description_for_methods_part text,
    device_id integer,
    device_type character varying,
    device_type_detail character varying,
    general_tags character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    helpers_uploaded boolean DEFAULT false,
    infrastructure_assignment character varying,
    institute character varying,
    maintenance_contract_available character varying,
    maintenance_scheduling character varying,
    measures_after_full_shut_down text,
    measures_after_short_shut_down text,
    measures_to_plan_offline_period text,
    name character varying,
    operation_mode character varying,
    operators jsonb,
    ontologies jsonb,
    planned_maintenance jsonb,
    policies_and_user_information text,
    restart_after_planned_offline_period text,
    room character varying,
    serial_number character varying,
    setup_descriptions jsonb,
    size character varying,
    short_label character varying,
    unexpected_maintenance jsonb,
    university_campus character varying,
    vendor_id character varying,
    vendor_url character varying,
    version_characterization text,
    version_doi character varying,
    version_doi_url character varying,
    version_identifier_type character varying,
    version_installation_start_date timestamp without time zone,
    version_installation_end_date timestamp without time zone,
    version_number character varying,
    weight character varying,
    weight_unit character varying,
    vendor_device_name character varying,
    vendor_device_id character varying,
    vendor_company_name character varying,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL,
    log_data jsonb
);


ALTER TABLE public.device_descriptions OWNER TO postgres;

--
-- Name: device_descriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.device_descriptions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.device_descriptions_id_seq OWNER TO postgres;

--
-- Name: device_descriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.device_descriptions_id_seq OWNED BY public.device_descriptions.id;


--
-- Name: device_metadata; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.device_metadata (
    id integer NOT NULL,
    device_id integer,
    doi character varying,
    url character varying,
    landing_page character varying,
    name character varying,
    type character varying,
    description character varying,
    publisher character varying,
    publication_year integer,
    manufacturers jsonb,
    owners jsonb,
    dates jsonb,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    doi_sequence integer,
    data_cite_prefix character varying,
    data_cite_created_at timestamp without time zone,
    data_cite_updated_at timestamp without time zone,
    data_cite_version integer,
    data_cite_last_response jsonb DEFAULT '{}'::jsonb,
    data_cite_state character varying DEFAULT 'draft'::character varying,
    data_cite_creator_name character varying
);


ALTER TABLE public.device_metadata OWNER TO postgres;

--
-- Name: device_metadata_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.device_metadata_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.device_metadata_id_seq OWNER TO postgres;

--
-- Name: device_metadata_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.device_metadata_id_seq OWNED BY public.device_metadata.id;


--
-- Name: devices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.devices (
    id bigint NOT NULL,
    name character varying,
    name_abbreviation character varying,
    first_name character varying,
    last_name character varying,
    email character varying,
    serial_number character varying,
    verification_status character varying DEFAULT 'none'::character varying,
    account_active boolean DEFAULT false,
    visibility boolean DEFAULT false,
    deleted_at timestamp without time zone,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL,
    datacollector_method character varying,
    datacollector_dir character varying,
    datacollector_host character varying,
    datacollector_user character varying,
    datacollector_authentication character varying,
    datacollector_number_of_files character varying,
    datacollector_key_name character varying,
    datacollector_user_level_selected boolean DEFAULT false,
    novnc_token character varying,
    novnc_target character varying,
    novnc_password character varying
);


ALTER TABLE public.devices OWNER TO postgres;

--
-- Name: devices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.devices_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.devices_id_seq OWNER TO postgres;

--
-- Name: devices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.devices_id_seq OWNED BY public.devices.id;


--
-- Name: element_klasses; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.element_klasses (
    id integer NOT NULL,
    name character varying,
    label character varying,
    "desc" character varying,
    icon_name character varying,
    is_active boolean DEFAULT true NOT NULL,
    klass_prefix character varying DEFAULT 'E'::character varying NOT NULL,
    is_generic boolean DEFAULT true NOT NULL,
    place integer DEFAULT 100 NOT NULL,
    properties_template jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    uuid character varying,
    properties_release jsonb DEFAULT '{}'::jsonb,
    released_at timestamp without time zone,
    identifier character varying,
    sync_time timestamp without time zone,
    updated_by integer,
    released_by integer,
    sync_by integer,
    admin_ids jsonb DEFAULT '{}'::jsonb,
    user_ids jsonb DEFAULT '{}'::jsonb,
    version character varying
);


ALTER TABLE public.element_klasses OWNER TO postgres;

--
-- Name: element_klasses_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.element_klasses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.element_klasses_id_seq OWNER TO postgres;

--
-- Name: element_klasses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.element_klasses_id_seq OWNED BY public.element_klasses.id;


--
-- Name: element_klasses_revisions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.element_klasses_revisions (
    id integer NOT NULL,
    element_klass_id integer,
    uuid character varying,
    properties_release jsonb DEFAULT '{}'::jsonb,
    released_at timestamp without time zone,
    released_by integer,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    version character varying
);


ALTER TABLE public.element_klasses_revisions OWNER TO postgres;

--
-- Name: element_klasses_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.element_klasses_revisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.element_klasses_revisions_id_seq OWNER TO postgres;

--
-- Name: element_klasses_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.element_klasses_revisions_id_seq OWNED BY public.element_klasses_revisions.id;


--
-- Name: element_tags; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.element_tags (
    id integer NOT NULL,
    taggable_type character varying,
    taggable_id integer,
    taggable_data jsonb,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE public.element_tags OWNER TO postgres;

--
-- Name: element_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.element_tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.element_tags_id_seq OWNER TO postgres;

--
-- Name: element_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.element_tags_id_seq OWNED BY public.element_tags.id;


--
-- Name: elemental_compositions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.elemental_compositions (
    id integer NOT NULL,
    sample_id integer NOT NULL,
    composition_type character varying NOT NULL,
    data public.hstore DEFAULT ''::public.hstore NOT NULL,
    loading double precision,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    log_data jsonb
);


ALTER TABLE public.elemental_compositions OWNER TO postgres;

--
-- Name: elemental_compositions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.elemental_compositions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.elemental_compositions_id_seq OWNER TO postgres;

--
-- Name: elemental_compositions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.elemental_compositions_id_seq OWNED BY public.elemental_compositions.id;


--
-- Name: elements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.elements (
    id integer NOT NULL,
    name character varying,
    element_klass_id integer,
    short_label character varying,
    properties jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    uuid character varying,
    klass_uuid character varying,
    properties_release jsonb,
    ancestry character varying
);


ALTER TABLE public.elements OWNER TO postgres;

--
-- Name: elements_elements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.elements_elements (
    id bigint NOT NULL,
    element_id integer,
    parent_id integer,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


ALTER TABLE public.elements_elements OWNER TO postgres;

--
-- Name: elements_elements_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.elements_elements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.elements_elements_id_seq OWNER TO postgres;

--
-- Name: elements_elements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.elements_elements_id_seq OWNED BY public.elements_elements.id;


--
-- Name: elements_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.elements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.elements_id_seq OWNER TO postgres;

--
-- Name: elements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.elements_id_seq OWNED BY public.elements.id;


--
-- Name: elements_revisions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.elements_revisions (
    id integer NOT NULL,
    element_id integer,
    uuid character varying,
    klass_uuid character varying,
    name character varying,
    properties jsonb DEFAULT '{}'::jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    properties_release jsonb
);


ALTER TABLE public.elements_revisions OWNER TO postgres;

--
-- Name: elements_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.elements_revisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.elements_revisions_id_seq OWNER TO postgres;

--
-- Name: elements_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.elements_revisions_id_seq OWNED BY public.elements_revisions.id;


--
-- Name: elements_samples; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.elements_samples (
    id integer NOT NULL,
    element_id integer,
    sample_id integer,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


ALTER TABLE public.elements_samples OWNER TO postgres;

--
-- Name: elements_samples_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.elements_samples_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.elements_samples_id_seq OWNER TO postgres;

--
-- Name: elements_samples_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.elements_samples_id_seq OWNED BY public.elements_samples.id;


--
-- Name: experiments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.experiments (
    id integer NOT NULL,
    type character varying(20),
    name character varying,
    description text,
    status character varying(20),
    parameter jsonb,
    user_id integer,
    device_id integer,
    container_id integer,
    experimentable_id integer,
    experimentable_type character varying,
    ancestry character varying,
    parent_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.experiments OWNER TO postgres;

--
-- Name: experiments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.experiments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.experiments_id_seq OWNER TO postgres;

--
-- Name: experiments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.experiments_id_seq OWNED BY public.experiments.id;


--
-- Name: fingerprints; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.fingerprints (
    id integer NOT NULL,
    fp0 bit(64),
    fp1 bit(64),
    fp2 bit(64),
    fp3 bit(64),
    fp4 bit(64),
    fp5 bit(64),
    fp6 bit(64),
    fp7 bit(64),
    fp8 bit(64),
    fp9 bit(64),
    fp10 bit(64),
    fp11 bit(64),
    fp12 bit(64),
    fp13 bit(64),
    fp14 bit(64),
    fp15 bit(64),
    num_set_bits smallint,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at time without time zone
);


ALTER TABLE public.fingerprints OWNER TO postgres;

--
-- Name: fingerprints_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.fingerprints_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.fingerprints_id_seq OWNER TO postgres;

--
-- Name: fingerprints_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.fingerprints_id_seq OWNED BY public.fingerprints.id;


--
-- Name: inventories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventories (
    id bigint NOT NULL,
    prefix character varying,
    name character varying,
    counter integer DEFAULT 0,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL
);


ALTER TABLE public.inventories OWNER TO postgres;

--
-- Name: inventories_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.inventories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.inventories_id_seq OWNER TO postgres;

--
-- Name: inventories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.inventories_id_seq OWNED BY public.inventories.id;


--
-- Name: ketcherails_amino_acids; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ketcherails_amino_acids (
    id integer NOT NULL,
    moderated_by integer,
    suggested_by integer,
    name character varying NOT NULL,
    molfile text NOT NULL,
    aid integer DEFAULT 1 NOT NULL,
    aid2 integer DEFAULT 1 NOT NULL,
    bid integer DEFAULT 1 NOT NULL,
    icon_path character varying,
    sprite_class character varying,
    status character varying,
    notes text,
    approved_at timestamp without time zone,
    rejected_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    icon_file_name character varying,
    icon_content_type character varying,
    icon_file_size integer,
    icon_updated_at timestamp without time zone
);


ALTER TABLE public.ketcherails_amino_acids OWNER TO postgres;

--
-- Name: ketcherails_amino_acids_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ketcherails_amino_acids_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ketcherails_amino_acids_id_seq OWNER TO postgres;

--
-- Name: ketcherails_amino_acids_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ketcherails_amino_acids_id_seq OWNED BY public.ketcherails_amino_acids.id;


--
-- Name: ketcherails_atom_abbreviations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ketcherails_atom_abbreviations (
    id integer NOT NULL,
    moderated_by integer,
    suggested_by integer,
    name character varying NOT NULL,
    molfile text NOT NULL,
    aid integer DEFAULT 1 NOT NULL,
    bid integer DEFAULT 1 NOT NULL,
    icon_path character varying,
    sprite_class character varying,
    status character varying,
    notes text,
    approved_at timestamp without time zone,
    rejected_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    icon_file_name character varying,
    icon_content_type character varying,
    icon_file_size integer,
    icon_updated_at timestamp without time zone,
    rtl_name character varying
);


ALTER TABLE public.ketcherails_atom_abbreviations OWNER TO postgres;

--
-- Name: ketcherails_atom_abbreviations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ketcherails_atom_abbreviations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ketcherails_atom_abbreviations_id_seq OWNER TO postgres;

--
-- Name: ketcherails_atom_abbreviations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ketcherails_atom_abbreviations_id_seq OWNED BY public.ketcherails_atom_abbreviations.id;


--
-- Name: ketcherails_common_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ketcherails_common_templates (
    id integer NOT NULL,
    moderated_by integer,
    suggested_by integer,
    name character varying NOT NULL,
    molfile text NOT NULL,
    icon_path character varying,
    sprite_class character varying,
    notes text,
    approved_at timestamp without time zone,
    rejected_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    template_category_id integer,
    status character varying,
    icon_file_name character varying,
    icon_content_type character varying,
    icon_file_size integer,
    icon_updated_at timestamp without time zone
);


ALTER TABLE public.ketcherails_common_templates OWNER TO postgres;

--
-- Name: ketcherails_common_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ketcherails_common_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ketcherails_common_templates_id_seq OWNER TO postgres;

--
-- Name: ketcherails_common_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ketcherails_common_templates_id_seq OWNED BY public.ketcherails_common_templates.id;


--
-- Name: ketcherails_custom_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ketcherails_custom_templates (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying NOT NULL,
    molfile text NOT NULL,
    icon_path character varying,
    sprite_class character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE public.ketcherails_custom_templates OWNER TO postgres;

--
-- Name: ketcherails_custom_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ketcherails_custom_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ketcherails_custom_templates_id_seq OWNER TO postgres;

--
-- Name: ketcherails_custom_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ketcherails_custom_templates_id_seq OWNED BY public.ketcherails_custom_templates.id;


--
-- Name: ketcherails_template_categories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ketcherails_template_categories (
    id integer NOT NULL,
    name character varying NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    icon_file_name character varying,
    icon_content_type character varying,
    icon_file_size integer,
    icon_updated_at timestamp without time zone,
    sprite_class character varying
);


ALTER TABLE public.ketcherails_template_categories OWNER TO postgres;

--
-- Name: ketcherails_template_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ketcherails_template_categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ketcherails_template_categories_id_seq OWNER TO postgres;

--
-- Name: ketcherails_template_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ketcherails_template_categories_id_seq OWNED BY public.ketcherails_template_categories.id;


--
-- Name: layer_tracks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.layer_tracks (
    id bigint NOT NULL,
    identifier character varying NOT NULL,
    name character varying,
    label character varying,
    description character varying,
    properties jsonb DEFAULT '{}'::jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_by integer,
    updated_at timestamp without time zone,
    deleted_by integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.layer_tracks OWNER TO postgres;

--
-- Name: layer_tracks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.layer_tracks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.layer_tracks_id_seq OWNER TO postgres;

--
-- Name: layer_tracks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.layer_tracks_id_seq OWNED BY public.layer_tracks.id;


--
-- Name: layers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.layers (
    id bigint NOT NULL,
    name character varying NOT NULL,
    label character varying,
    description character varying,
    properties jsonb DEFAULT '{}'::jsonb NOT NULL,
    identifier character varying NOT NULL,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_by integer,
    updated_at timestamp without time zone,
    deleted_by integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.layers OWNER TO postgres;

--
-- Name: layers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.layers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.layers_id_seq OWNER TO postgres;

--
-- Name: layers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.layers_id_seq OWNED BY public.layers.id;


--
-- Name: literals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.literals (
    id integer NOT NULL,
    literature_id integer,
    element_id integer,
    element_type character varying(40),
    category character varying(40),
    user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    litype character varying
);


ALTER TABLE public.literals OWNER TO postgres;

--
-- Name: literatures; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.literatures (
    id integer NOT NULL,
    title character varying,
    url character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    refs jsonb,
    doi character varying,
    isbn character varying
);


ALTER TABLE public.literatures OWNER TO postgres;

--
-- Name: reactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reactions (
    id integer NOT NULL,
    name character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    description text,
    timestamp_start character varying,
    timestamp_stop character varying,
    observation text,
    purification character varying[] DEFAULT '{}'::character varying[],
    dangerous_products character varying[] DEFAULT '{}'::character varying[],
    tlc_solvents character varying,
    tlc_description text,
    rf_value character varying,
    temperature jsonb DEFAULT '{"data": [], "userText": "", "valueUnit": "°C"}'::jsonb,
    status character varying,
    reaction_svg_file character varying,
    solvent character varying,
    deleted_at timestamp without time zone,
    short_label character varying,
    created_by integer,
    role character varying,
    origin jsonb,
    rinchi_string text,
    rinchi_long_key text,
    rinchi_short_key character varying,
    rinchi_web_key character varying,
    duration character varying,
    rxno character varying,
    conditions character varying,
    variations jsonb DEFAULT '{}'::jsonb,
    plain_text_description text,
    plain_text_observation text,
    gaseous boolean DEFAULT false,
    vessel_size jsonb DEFAULT '{"unit": "ml", "amount": null}'::jsonb,
    log_data jsonb
);


ALTER TABLE public.reactions OWNER TO postgres;

--
-- Name: samples; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.samples (
    id integer NOT NULL,
    name character varying,
    target_amount_value double precision DEFAULT 0.0,
    target_amount_unit character varying DEFAULT 'g'::character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    description text DEFAULT ''::text,
    molecule_id integer,
    molfile bytea,
    purity double precision DEFAULT 1.0,
    deprecated_solvent character varying DEFAULT ''::character varying,
    impurities character varying DEFAULT ''::character varying,
    location character varying DEFAULT ''::character varying,
    is_top_secret boolean DEFAULT false,
    ancestry character varying,
    external_label character varying DEFAULT ''::character varying,
    created_by integer,
    short_label character varying,
    real_amount_value double precision,
    real_amount_unit character varying,
    imported_readout character varying,
    deleted_at timestamp without time zone,
    sample_svg_file character varying,
    user_id integer,
    identifier character varying,
    density double precision DEFAULT 0.0,
    melting_point numrange,
    boiling_point numrange,
    fingerprint_id integer,
    xref jsonb DEFAULT '{}'::jsonb,
    molarity_value double precision DEFAULT 0.0,
    molarity_unit character varying DEFAULT 'M'::character varying,
    molecule_name_id integer,
    molfile_version character varying(20),
    stereo jsonb,
    metrics character varying DEFAULT 'mmm'::character varying,
    decoupled boolean DEFAULT false NOT NULL,
    molecular_mass double precision,
    sum_formula character varying,
    solvent jsonb,
    dry_solvent boolean DEFAULT false,
    inventory_sample boolean DEFAULT false,
    log_data jsonb
);


ALTER TABLE public.samples OWNER TO postgres;

--
-- Name: literal_groups; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.literal_groups AS
 SELECT lits.element_type,
    lits.element_id,
    lits.literature_id,
    lits.category,
    lits.count,
    literatures.title,
    literatures.doi,
    literatures.url,
    literatures.refs,
    COALESCE(reactions.short_label, samples.short_label) AS short_label,
    COALESCE(reactions.name, samples.name) AS name,
    samples.external_label,
    COALESCE(reactions.updated_at, samples.updated_at) AS element_updated_at
   FROM (((( SELECT literals.element_type,
            literals.element_id,
            literals.literature_id,
            literals.category,
            count(*) AS count
           FROM public.literals
          GROUP BY literals.element_type, literals.element_id, literals.literature_id, literals.category) lits
     JOIN public.literatures ON ((lits.literature_id = literatures.id)))
     LEFT JOIN public.samples ON ((((lits.element_type)::text = 'Sample'::text) AND (lits.element_id = samples.id))))
     LEFT JOIN public.reactions ON ((((lits.element_type)::text = 'Reaction'::text) AND (lits.element_id = reactions.id))));


ALTER VIEW public.literal_groups OWNER TO postgres;

--
-- Name: literals_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.literals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.literals_id_seq OWNER TO postgres;

--
-- Name: literals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.literals_id_seq OWNED BY public.literals.id;


--
-- Name: literatures_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.literatures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.literatures_id_seq OWNER TO postgres;

--
-- Name: literatures_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.literatures_id_seq OWNED BY public.literatures.id;


--
-- Name: matrices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.matrices (
    id integer NOT NULL,
    name character varying NOT NULL,
    enabled boolean DEFAULT false,
    label character varying,
    include_ids integer[] DEFAULT '{}'::integer[],
    exclude_ids integer[] DEFAULT '{}'::integer[],
    configs jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


ALTER TABLE public.matrices OWNER TO postgres;

--
-- Name: matrices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.matrices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.matrices_id_seq OWNER TO postgres;

--
-- Name: matrices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.matrices_id_seq OWNED BY public.matrices.id;


--
-- Name: measurements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.measurements (
    id bigint NOT NULL,
    description character varying NOT NULL,
    value numeric NOT NULL,
    unit character varying NOT NULL,
    deleted_at timestamp without time zone,
    well_id bigint,
    sample_id bigint NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    source_type character varying,
    source_id bigint
);


ALTER TABLE public.measurements OWNER TO postgres;

--
-- Name: measurements_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.measurements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.measurements_id_seq OWNER TO postgres;

--
-- Name: measurements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.measurements_id_seq OWNED BY public.measurements.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    channel_id integer,
    content jsonb NOT NULL,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.messages OWNER TO postgres;

--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.messages_id_seq OWNER TO postgres;

--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: metadata; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.metadata (
    id bigint NOT NULL,
    collection_id integer,
    metadata jsonb,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.metadata OWNER TO postgres;

--
-- Name: metadata_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.metadata_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.metadata_id_seq OWNER TO postgres;

--
-- Name: metadata_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.metadata_id_seq OWNED BY public.metadata.id;


--
-- Name: molecule_names; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.molecule_names (
    id integer NOT NULL,
    molecule_id integer,
    user_id integer,
    description text,
    name character varying NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.molecule_names OWNER TO postgres;

--
-- Name: molecule_names_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.molecule_names_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.molecule_names_id_seq OWNER TO postgres;

--
-- Name: molecule_names_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.molecule_names_id_seq OWNED BY public.molecule_names.id;


--
-- Name: molecules; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.molecules (
    id integer NOT NULL,
    inchikey character varying,
    inchistring character varying,
    density double precision DEFAULT 0.0,
    molecular_weight double precision,
    molfile bytea,
    melting_point double precision,
    boiling_point double precision,
    sum_formular character varying,
    names character varying[] DEFAULT '{}'::character varying[],
    iupac_name character varying,
    molecule_svg_file character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    is_partial boolean DEFAULT false NOT NULL,
    exact_molecular_weight double precision,
    cano_smiles character varying,
    cas text,
    molfile_version character varying(20)
);


ALTER TABLE public.molecules OWNER TO postgres;

--
-- Name: molecules_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.molecules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.molecules_id_seq OWNER TO postgres;

--
-- Name: molecules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.molecules_id_seq OWNED BY public.molecules.id;


--
-- Name: nmr_sim_nmr_simulations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.nmr_sim_nmr_simulations (
    id integer NOT NULL,
    molecule_id integer,
    path_1h text,
    path_13c text,
    source text,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.nmr_sim_nmr_simulations OWNER TO postgres;

--
-- Name: nmr_sim_nmr_simulations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.nmr_sim_nmr_simulations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.nmr_sim_nmr_simulations_id_seq OWNER TO postgres;

--
-- Name: nmr_sim_nmr_simulations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.nmr_sim_nmr_simulations_id_seq OWNED BY public.nmr_sim_nmr_simulations.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    message_id integer,
    user_id integer,
    is_ack integer DEFAULT 0,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.notifications OWNER TO postgres;

--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notifications_id_seq OWNER TO postgres;

--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying DEFAULT ''::character varying NOT NULL,
    encrypted_password character varying DEFAULT ''::character varying NOT NULL,
    reset_password_token character varying,
    reset_password_sent_at timestamp without time zone,
    remember_created_at timestamp without time zone,
    sign_in_count integer DEFAULT 0 NOT NULL,
    current_sign_in_at timestamp without time zone,
    last_sign_in_at timestamp without time zone,
    current_sign_in_ip inet,
    last_sign_in_ip inet,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    name character varying,
    first_name character varying NOT NULL,
    last_name character varying NOT NULL,
    deleted_at timestamp without time zone,
    counters public.hstore DEFAULT '"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"'::public.hstore NOT NULL,
    name_abbreviation character varying(12),
    type character varying DEFAULT 'Person'::character varying,
    reaction_name_prefix character varying(3) DEFAULT 'R'::character varying,
    confirmation_token character varying,
    confirmed_at timestamp without time zone,
    confirmation_sent_at timestamp without time zone,
    unconfirmed_email character varying,
    layout public.hstore DEFAULT '"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"'::public.hstore NOT NULL,
    selected_device_id integer,
    failed_attempts integer DEFAULT 0 NOT NULL,
    unlock_token character varying,
    locked_at timestamp without time zone,
    account_active boolean,
    matrix integer DEFAULT 0,
    providers jsonb,
    is_super_device boolean DEFAULT false,
    used_space bigint DEFAULT 0,
    allocated_space bigint DEFAULT 0
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: notify_messages; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.notify_messages AS
 SELECT notifications.id,
    messages.id AS message_id,
    channels.subject,
    messages.content,
    notifications.created_at,
    notifications.updated_at,
    users.id AS sender_id,
    (((users.first_name)::text || chr(32)) || (users.last_name)::text) AS sender_name,
    channels.channel_type,
    notifications.user_id AS receiver_id,
    notifications.is_ack
   FROM public.messages,
    public.notifications,
    public.channels,
    public.users
  WHERE ((channels.id = messages.channel_id) AND (messages.id = notifications.message_id) AND (users.id = messages.created_by));


ALTER VIEW public.notify_messages OWNER TO postgres;

--
-- Name: ols_terms; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ols_terms (
    id integer NOT NULL,
    owl_name character varying,
    term_id character varying,
    ancestry character varying,
    ancestry_term_id character varying,
    label character varying,
    synonym character varying,
    synonyms jsonb,
    "desc" character varying,
    metadata jsonb,
    is_enabled boolean DEFAULT true,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.ols_terms OWNER TO postgres;

--
-- Name: ols_terms_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ols_terms_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ols_terms_id_seq OWNER TO postgres;

--
-- Name: ols_terms_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ols_terms_id_seq OWNED BY public.ols_terms.id;


--
-- Name: pg_search_documents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.pg_search_documents (
    id integer NOT NULL,
    content text,
    searchable_type character varying,
    searchable_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.pg_search_documents OWNER TO postgres;

--
-- Name: pg_search_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.pg_search_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pg_search_documents_id_seq OWNER TO postgres;

--
-- Name: pg_search_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.pg_search_documents_id_seq OWNED BY public.pg_search_documents.id;


--
-- Name: predictions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.predictions (
    id integer NOT NULL,
    predictable_type character varying,
    predictable_id integer,
    decision jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE public.predictions OWNER TO postgres;

--
-- Name: predictions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.predictions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.predictions_id_seq OWNER TO postgres;

--
-- Name: predictions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.predictions_id_seq OWNED BY public.predictions.id;


--
-- Name: private_notes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.private_notes (
    id bigint NOT NULL,
    content character varying,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    noteable_id integer,
    noteable_type character varying
);


ALTER TABLE public.private_notes OWNER TO postgres;

--
-- Name: private_notes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.private_notes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.private_notes_id_seq OWNER TO postgres;

--
-- Name: private_notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.private_notes_id_seq OWNED BY public.private_notes.id;


--
-- Name: profiles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.profiles (
    id integer NOT NULL,
    show_external_name boolean DEFAULT false,
    user_id integer NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    data jsonb DEFAULT '{}'::jsonb NOT NULL,
    curation integer DEFAULT 2,
    show_sample_name boolean DEFAULT false,
    show_sample_short_label boolean DEFAULT false
);


ALTER TABLE public.profiles OWNER TO postgres;

--
-- Name: profiles_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.profiles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.profiles_id_seq OWNER TO postgres;

--
-- Name: profiles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.profiles_id_seq OWNED BY public.profiles.id;


--
-- Name: reactions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reactions_id_seq OWNER TO postgres;

--
-- Name: reactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reactions_id_seq OWNED BY public.reactions.id;


--
-- Name: reactions_samples; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reactions_samples (
    id integer NOT NULL,
    reaction_id integer,
    sample_id integer,
    reference boolean,
    equivalent double precision,
    "position" integer,
    type character varying,
    deleted_at timestamp without time zone,
    waste boolean DEFAULT false,
    coefficient double precision DEFAULT 1.0,
    show_label boolean DEFAULT false NOT NULL,
    gas_type integer DEFAULT 0,
    gas_phase_data jsonb DEFAULT '{"time": {"unit": "h", "value": null}, "temperature": {"unit": "°C", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}'::jsonb,
    conversion_rate double precision,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    log_data jsonb
);


ALTER TABLE public.reactions_samples OWNER TO postgres;

--
-- Name: reactions_samples_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reactions_samples_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reactions_samples_id_seq OWNER TO postgres;

--
-- Name: reactions_samples_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reactions_samples_id_seq OWNED BY public.reactions_samples.id;


--
-- Name: report_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.report_templates (
    id integer NOT NULL,
    name character varying NOT NULL,
    report_type character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    attachment_id integer
);


ALTER TABLE public.report_templates OWNER TO postgres;

--
-- Name: report_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.report_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.report_templates_id_seq OWNER TO postgres;

--
-- Name: report_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.report_templates_id_seq OWNED BY public.report_templates.id;


--
-- Name: reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reports (
    id integer NOT NULL,
    author_id integer,
    file_name character varying,
    file_description text,
    configs text,
    sample_settings text,
    reaction_settings text,
    objects text,
    img_format character varying,
    file_path character varying,
    generated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    template character varying DEFAULT 'standard'::character varying,
    mol_serials text DEFAULT '--- []
'::text,
    si_reaction_settings text DEFAULT '---
Name: true
CAS: true
Formula: true
Smiles: true
InCHI: true
Molecular Mass: true
Exact Mass: true
EA: true
'::text,
    prd_atts text DEFAULT '--- []
'::text,
    report_templates_id integer
);


ALTER TABLE public.reports OWNER TO postgres;

--
-- Name: reports_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reports_id_seq OWNER TO postgres;

--
-- Name: reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reports_id_seq OWNED BY public.reports.id;


--
-- Name: reports_users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reports_users (
    id integer NOT NULL,
    user_id integer,
    report_id integer,
    downloaded_at timestamp without time zone,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.reports_users OWNER TO postgres;

--
-- Name: reports_users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reports_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reports_users_id_seq OWNER TO postgres;

--
-- Name: reports_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reports_users_id_seq OWNED BY public.reports_users.id;


--
-- Name: research_plan_metadata; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.research_plan_metadata (
    id integer NOT NULL,
    research_plan_id integer,
    doi character varying,
    url character varying,
    landing_page character varying,
    title character varying,
    type character varying,
    publisher character varying,
    publication_year integer,
    dates jsonb,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    data_cite_prefix character varying,
    data_cite_created_at timestamp without time zone,
    data_cite_updated_at timestamp without time zone,
    data_cite_version integer,
    data_cite_last_response jsonb DEFAULT '{}'::jsonb,
    data_cite_state character varying DEFAULT 'draft'::character varying,
    data_cite_creator_name character varying,
    description jsonb,
    creator text,
    affiliation text,
    contributor text,
    language character varying,
    rights text,
    format character varying,
    version character varying,
    geo_location jsonb,
    funding_reference jsonb,
    subject text,
    alternate_identifier jsonb,
    related_identifier jsonb,
    log_data jsonb
);


ALTER TABLE public.research_plan_metadata OWNER TO postgres;

--
-- Name: research_plan_metadata_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.research_plan_metadata_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.research_plan_metadata_id_seq OWNER TO postgres;

--
-- Name: research_plan_metadata_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.research_plan_metadata_id_seq OWNED BY public.research_plan_metadata.id;


--
-- Name: research_plan_table_schemas; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.research_plan_table_schemas (
    id integer NOT NULL,
    name character varying,
    value jsonb,
    created_by integer NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.research_plan_table_schemas OWNER TO postgres;

--
-- Name: research_plan_table_schemas_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.research_plan_table_schemas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.research_plan_table_schemas_id_seq OWNER TO postgres;

--
-- Name: research_plan_table_schemas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.research_plan_table_schemas_id_seq OWNED BY public.research_plan_table_schemas.id;


--
-- Name: research_plans; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.research_plans (
    id integer NOT NULL,
    name character varying NOT NULL,
    created_by integer NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    body jsonb,
    log_data jsonb
);


ALTER TABLE public.research_plans OWNER TO postgres;

--
-- Name: research_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.research_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.research_plans_id_seq OWNER TO postgres;

--
-- Name: research_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.research_plans_id_seq OWNED BY public.research_plans.id;


--
-- Name: research_plans_screens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.research_plans_screens (
    screen_id bigint NOT NULL,
    research_plan_id bigint NOT NULL,
    id bigint NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


ALTER TABLE public.research_plans_screens OWNER TO postgres;

--
-- Name: research_plans_screens_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.research_plans_screens_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.research_plans_screens_id_seq OWNER TO postgres;

--
-- Name: research_plans_screens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.research_plans_screens_id_seq OWNED BY public.research_plans_screens.id;


--
-- Name: research_plans_wellplates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.research_plans_wellplates (
    research_plan_id bigint NOT NULL,
    wellplate_id bigint NOT NULL,
    id bigint NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    log_data jsonb
);


ALTER TABLE public.research_plans_wellplates OWNER TO postgres;

--
-- Name: research_plans_wellplates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.research_plans_wellplates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.research_plans_wellplates_id_seq OWNER TO postgres;

--
-- Name: research_plans_wellplates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.research_plans_wellplates_id_seq OWNED BY public.research_plans_wellplates.id;


--
-- Name: residues; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.residues (
    id integer NOT NULL,
    sample_id integer,
    residue_type character varying,
    custom_info public.hstore,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    log_data jsonb
);


ALTER TABLE public.residues OWNER TO postgres;

--
-- Name: residues_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.residues_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.residues_id_seq OWNER TO postgres;

--
-- Name: residues_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.residues_id_seq OWNED BY public.residues.id;


--
-- Name: sample_tasks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sample_tasks (
    id bigint NOT NULL,
    result_value double precision,
    result_unit character varying DEFAULT 'g'::character varying NOT NULL,
    description character varying,
    creator_id bigint NOT NULL,
    sample_id bigint,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    required_scan_results integer DEFAULT 1 NOT NULL
);


ALTER TABLE public.sample_tasks OWNER TO postgres;

--
-- Name: sample_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sample_tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sample_tasks_id_seq OWNER TO postgres;

--
-- Name: sample_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sample_tasks_id_seq OWNED BY public.sample_tasks.id;


--
-- Name: samples_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.samples_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.samples_id_seq OWNER TO postgres;

--
-- Name: samples_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.samples_id_seq OWNED BY public.samples.id;


--
-- Name: scan_results; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.scan_results (
    id bigint NOT NULL,
    measurement_value double precision NOT NULL,
    measurement_unit character varying DEFAULT 'g'::character varying NOT NULL,
    title character varying,
    "position" integer DEFAULT 0 NOT NULL,
    sample_task_id bigint,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL
);


ALTER TABLE public.scan_results OWNER TO postgres;

--
-- Name: scan_results_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.scan_results_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scan_results_id_seq OWNER TO postgres;

--
-- Name: scan_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.scan_results_id_seq OWNED BY public.scan_results.id;


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


ALTER TABLE public.schema_migrations OWNER TO postgres;

--
-- Name: scifinder_n_credentials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.scifinder_n_credentials (
    id bigint NOT NULL,
    access_token character varying NOT NULL,
    refresh_token character varying,
    expires_at timestamp without time zone NOT NULL,
    created_by integer NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.scifinder_n_credentials OWNER TO postgres;

--
-- Name: scifinder_n_credentials_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.scifinder_n_credentials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scifinder_n_credentials_id_seq OWNER TO postgres;

--
-- Name: scifinder_n_credentials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.scifinder_n_credentials_id_seq OWNED BY public.scifinder_n_credentials.id;


--
-- Name: screens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.screens (
    id integer NOT NULL,
    description character varying,
    name character varying,
    result character varying,
    collaborator character varying,
    conditions character varying,
    requirements character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    component_graph_data jsonb DEFAULT '{}'::jsonb,
    plain_text_description text,
    log_data jsonb
);


ALTER TABLE public.screens OWNER TO postgres;

--
-- Name: screens_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.screens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.screens_id_seq OWNER TO postgres;

--
-- Name: screens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.screens_id_seq OWNED BY public.screens.id;


--
-- Name: screens_wellplates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.screens_wellplates (
    id integer NOT NULL,
    screen_id integer,
    wellplate_id integer,
    deleted_at timestamp without time zone
);


ALTER TABLE public.screens_wellplates OWNER TO postgres;

--
-- Name: screens_wellplates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.screens_wellplates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.screens_wellplates_id_seq OWNER TO postgres;

--
-- Name: screens_wellplates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.screens_wellplates_id_seq OWNED BY public.screens_wellplates.id;


--
-- Name: segment_klasses; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.segment_klasses (
    id integer NOT NULL,
    element_klass_id integer,
    label character varying NOT NULL,
    "desc" character varying,
    properties_template jsonb,
    is_active boolean DEFAULT true NOT NULL,
    place integer DEFAULT 100 NOT NULL,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    uuid character varying,
    properties_release jsonb DEFAULT '{}'::jsonb,
    released_at timestamp without time zone,
    identifier character varying,
    sync_time timestamp without time zone,
    updated_by integer,
    released_by integer,
    sync_by integer,
    admin_ids jsonb DEFAULT '{}'::jsonb,
    user_ids jsonb DEFAULT '{}'::jsonb,
    version character varying
);


ALTER TABLE public.segment_klasses OWNER TO postgres;

--
-- Name: segment_klasses_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.segment_klasses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.segment_klasses_id_seq OWNER TO postgres;

--
-- Name: segment_klasses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.segment_klasses_id_seq OWNED BY public.segment_klasses.id;


--
-- Name: segment_klasses_revisions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.segment_klasses_revisions (
    id integer NOT NULL,
    segment_klass_id integer,
    uuid character varying,
    properties_release jsonb DEFAULT '{}'::jsonb,
    released_at timestamp without time zone,
    released_by integer,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    version character varying
);


ALTER TABLE public.segment_klasses_revisions OWNER TO postgres;

--
-- Name: segment_klasses_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.segment_klasses_revisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.segment_klasses_revisions_id_seq OWNER TO postgres;

--
-- Name: segment_klasses_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.segment_klasses_revisions_id_seq OWNED BY public.segment_klasses_revisions.id;


--
-- Name: segments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.segments (
    id integer NOT NULL,
    segment_klass_id integer,
    element_type character varying,
    element_id integer,
    properties jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    uuid character varying,
    klass_uuid character varying,
    properties_release jsonb
);


ALTER TABLE public.segments OWNER TO postgres;

--
-- Name: segments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.segments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.segments_id_seq OWNER TO postgres;

--
-- Name: segments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.segments_id_seq OWNED BY public.segments.id;


--
-- Name: segments_revisions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.segments_revisions (
    id integer NOT NULL,
    segment_id integer,
    uuid character varying,
    klass_uuid character varying,
    properties jsonb DEFAULT '{}'::jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    properties_release jsonb
);


ALTER TABLE public.segments_revisions OWNER TO postgres;

--
-- Name: segments_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.segments_revisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.segments_revisions_id_seq OWNER TO postgres;

--
-- Name: segments_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.segments_revisions_id_seq OWNED BY public.segments_revisions.id;


--
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.subscriptions (
    id integer NOT NULL,
    channel_id integer,
    user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.subscriptions OWNER TO postgres;

--
-- Name: subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.subscriptions_id_seq OWNER TO postgres;

--
-- Name: subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.subscriptions_id_seq OWNED BY public.subscriptions.id;


--
-- Name: sync_collections_users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sync_collections_users (
    id integer NOT NULL,
    user_id integer,
    collection_id integer,
    shared_by_id integer,
    permission_level integer DEFAULT 0,
    sample_detail_level integer DEFAULT 0,
    reaction_detail_level integer DEFAULT 0,
    wellplate_detail_level integer DEFAULT 0,
    screen_detail_level integer DEFAULT 0,
    fake_ancestry character varying,
    researchplan_detail_level integer DEFAULT 10,
    label character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    element_detail_level integer DEFAULT 10,
    celllinesample_detail_level integer DEFAULT 10,
    devicedescription_detail_level integer DEFAULT 10
);


ALTER TABLE public.sync_collections_users OWNER TO postgres;

--
-- Name: sync_collections_users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sync_collections_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sync_collections_users_id_seq OWNER TO postgres;

--
-- Name: sync_collections_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sync_collections_users_id_seq OWNED BY public.sync_collections_users.id;


--
-- Name: text_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.text_templates (
    id integer NOT NULL,
    type character varying,
    user_id integer NOT NULL,
    name character varying,
    data jsonb DEFAULT '{}'::jsonb,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.text_templates OWNER TO postgres;

--
-- Name: text_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.text_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.text_templates_id_seq OWNER TO postgres;

--
-- Name: text_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.text_templates_id_seq OWNED BY public.text_templates.id;


--
-- Name: third_party_apps; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.third_party_apps (
    id bigint NOT NULL,
    url character varying,
    name character varying(100) NOT NULL,
    file_types character varying(100),
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL
);


ALTER TABLE public.third_party_apps OWNER TO postgres;

--
-- Name: third_party_apps_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.third_party_apps_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.third_party_apps_id_seq OWNER TO postgres;

--
-- Name: third_party_apps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.third_party_apps_id_seq OWNED BY public.third_party_apps.id;


--
-- Name: user_affiliations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_affiliations (
    id integer NOT NULL,
    user_id integer,
    affiliation_id integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone,
    "from" date,
    "to" date,
    main boolean
);


ALTER TABLE public.user_affiliations OWNER TO postgres;

--
-- Name: user_affiliations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_affiliations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_affiliations_id_seq OWNER TO postgres;

--
-- Name: user_affiliations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_affiliations_id_seq OWNED BY public.user_affiliations.id;


--
-- Name: user_labels; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_labels (
    id integer NOT NULL,
    user_id integer,
    title character varying NOT NULL,
    description character varying,
    color character varying NOT NULL,
    access_level integer DEFAULT 0,
    "position" integer DEFAULT 10,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


ALTER TABLE public.user_labels OWNER TO postgres;

--
-- Name: user_labels_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_labels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_labels_id_seq OWNER TO postgres;

--
-- Name: user_labels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_labels_id_seq OWNED BY public.user_labels.id;


--
-- Name: users_admins; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users_admins (
    id integer NOT NULL,
    user_id integer,
    admin_id integer
);


ALTER TABLE public.users_admins OWNER TO postgres;

--
-- Name: users_admins_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_admins_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_admins_id_seq OWNER TO postgres;

--
-- Name: users_admins_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_admins_id_seq OWNED BY public.users_admins.id;


--
-- Name: users_devices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users_devices (
    id integer NOT NULL,
    user_id integer,
    device_id integer
);


ALTER TABLE public.users_devices OWNER TO postgres;

--
-- Name: users_devices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_devices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_devices_id_seq OWNER TO postgres;

--
-- Name: users_devices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_devices_id_seq OWNED BY public.users_devices.id;


--
-- Name: users_groups; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users_groups (
    id integer NOT NULL,
    user_id integer,
    group_id integer
);


ALTER TABLE public.users_groups OWNER TO postgres;

--
-- Name: users_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_groups_id_seq OWNER TO postgres;

--
-- Name: users_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_groups_id_seq OWNED BY public.users_groups.id;


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: v_samples_collections; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.v_samples_collections AS
 SELECT cols.id AS cols_id,
    cols.user_id AS cols_user_id,
    cols.sample_detail_level AS cols_sample_detail_level,
    cols.wellplate_detail_level AS cols_wellplate_detail_level,
    cols.shared_by_id AS cols_shared_by_id,
    cols.is_shared AS cols_is_shared,
    samples.id AS sams_id,
    samples.name AS sams_name
   FROM ((public.collections cols
     JOIN public.collections_samples col_samples ON (((col_samples.collection_id = cols.id) AND (col_samples.deleted_at IS NULL))))
     JOIN public.samples ON (((samples.id = col_samples.sample_id) AND (samples.deleted_at IS NULL))))
  WHERE (cols.deleted_at IS NULL);


ALTER VIEW public.v_samples_collections OWNER TO postgres;

--
-- Name: vessel_templates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vessel_templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying,
    details character varying,
    material_details character varying,
    material_type character varying,
    vessel_type character varying,
    volume_amount double precision,
    volume_unit character varying,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL,
    deleted_at timestamp without time zone,
    weight_amount double precision,
    weight_unit character varying
);


ALTER TABLE public.vessel_templates OWNER TO postgres;

--
-- Name: vessels; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vessels (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    vessel_template_id uuid,
    user_id bigint,
    name character varying,
    description character varying,
    short_label character varying,
    created_at timestamp(6) without time zone NOT NULL,
    updated_at timestamp(6) without time zone NOT NULL,
    deleted_at timestamp without time zone,
    bar_code character varying,
    qr_code character varying
);


ALTER TABLE public.vessels OWNER TO postgres;

--
-- Name: vocabularies; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vocabularies (
    id bigint NOT NULL,
    identifier character varying,
    name character varying,
    label character varying,
    field_type character varying,
    description character varying,
    opid integer DEFAULT 0,
    term_id character varying,
    source character varying,
    source_id character varying,
    layer_id character varying,
    field_id character varying,
    properties jsonb DEFAULT '{}'::jsonb,
    created_by integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


ALTER TABLE public.vocabularies OWNER TO postgres;

--
-- Name: vocabularies_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.vocabularies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.vocabularies_id_seq OWNER TO postgres;

--
-- Name: vocabularies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.vocabularies_id_seq OWNED BY public.vocabularies.id;


--
-- Name: wellplates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.wellplates (
    id integer NOT NULL,
    name character varying,
    description character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    short_label character varying,
    readout_titles jsonb DEFAULT '["Readout"]'::jsonb,
    plain_text_description text,
    width integer DEFAULT 12,
    height integer DEFAULT 8,
    log_data jsonb
);


ALTER TABLE public.wellplates OWNER TO postgres;

--
-- Name: wellplates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.wellplates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.wellplates_id_seq OWNER TO postgres;

--
-- Name: wellplates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.wellplates_id_seq OWNED BY public.wellplates.id;


--
-- Name: wells; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.wells (
    id integer NOT NULL,
    sample_id integer,
    wellplate_id integer NOT NULL,
    position_x integer,
    position_y integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    additive character varying,
    deleted_at timestamp without time zone,
    readouts jsonb DEFAULT '[{"unit": "", "value": ""}]'::jsonb,
    label character varying DEFAULT 'Molecular structure'::character varying NOT NULL,
    color_code character varying,
    log_data jsonb
);


ALTER TABLE public.wells OWNER TO postgres;

--
-- Name: wells_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.wells_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.wells_id_seq OWNER TO postgres;

--
-- Name: wells_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.wells_id_seq OWNED BY public.wells.id;


--
-- Name: mols; Type: TABLE; Schema: rdkit; Owner: postgres
--

CREATE TABLE rdkit.mols (
    id integer,
    m public.mol
);


ALTER TABLE rdkit.mols OWNER TO postgres;

--
-- Name: affiliations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.affiliations ALTER COLUMN id SET DEFAULT nextval('public.affiliations_id_seq'::regclass);


--
-- Name: analyses_experiments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.analyses_experiments ALTER COLUMN id SET DEFAULT nextval('public.analyses_experiments_id_seq'::regclass);


--
-- Name: attachments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.attachments ALTER COLUMN id SET DEFAULT nextval('public.attachments_id_seq'::regclass);


--
-- Name: authentication_keys id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.authentication_keys ALTER COLUMN id SET DEFAULT nextval('public.authentication_keys_id_seq'::regclass);


--
-- Name: calendar_entries id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calendar_entries ALTER COLUMN id SET DEFAULT nextval('public.calendar_entries_id_seq'::regclass);


--
-- Name: calendar_entry_notifications id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calendar_entry_notifications ALTER COLUMN id SET DEFAULT nextval('public.calendar_entry_notifications_id_seq'::regclass);


--
-- Name: cellline_materials id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cellline_materials ALTER COLUMN id SET DEFAULT nextval('public.cellline_materials_id_seq'::regclass);


--
-- Name: cellline_samples id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cellline_samples ALTER COLUMN id SET DEFAULT nextval('public.cellline_samples_id_seq'::regclass);


--
-- Name: channels id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channels ALTER COLUMN id SET DEFAULT nextval('public.channels_id_seq'::regclass);


--
-- Name: chemicals id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chemicals ALTER COLUMN id SET DEFAULT nextval('public.chemicals_id_seq'::regclass);


--
-- Name: collections id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections ALTER COLUMN id SET DEFAULT nextval('public.collections_id_seq'::regclass);


--
-- Name: collections_celllines id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_celllines ALTER COLUMN id SET DEFAULT nextval('public.collections_celllines_id_seq'::regclass);


--
-- Name: collections_device_descriptions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_device_descriptions ALTER COLUMN id SET DEFAULT nextval('public.collections_device_descriptions_id_seq'::regclass);


--
-- Name: collections_elements id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_elements ALTER COLUMN id SET DEFAULT nextval('public.collections_elements_id_seq'::regclass);


--
-- Name: collections_reactions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_reactions ALTER COLUMN id SET DEFAULT nextval('public.collections_reactions_id_seq'::regclass);


--
-- Name: collections_research_plans id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_research_plans ALTER COLUMN id SET DEFAULT nextval('public.collections_research_plans_id_seq'::regclass);


--
-- Name: collections_samples id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_samples ALTER COLUMN id SET DEFAULT nextval('public.collections_samples_id_seq'::regclass);


--
-- Name: collections_screens id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_screens ALTER COLUMN id SET DEFAULT nextval('public.collections_screens_id_seq'::regclass);


--
-- Name: collections_wellplates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_wellplates ALTER COLUMN id SET DEFAULT nextval('public.collections_wellplates_id_seq'::regclass);


--
-- Name: collector_errors id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collector_errors ALTER COLUMN id SET DEFAULT nextval('public.collector_errors_id_seq'::regclass);


--
-- Name: comments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comments ALTER COLUMN id SET DEFAULT nextval('public.comments_id_seq'::regclass);


--
-- Name: computed_props id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.computed_props ALTER COLUMN id SET DEFAULT nextval('public.computed_props_id_seq'::regclass);


--
-- Name: containers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.containers ALTER COLUMN id SET DEFAULT nextval('public.containers_id_seq'::regclass);


--
-- Name: dataset_klasses id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dataset_klasses ALTER COLUMN id SET DEFAULT nextval('public.dataset_klasses_id_seq'::regclass);


--
-- Name: dataset_klasses_revisions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dataset_klasses_revisions ALTER COLUMN id SET DEFAULT nextval('public.dataset_klasses_revisions_id_seq'::regclass);


--
-- Name: datasets id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.datasets ALTER COLUMN id SET DEFAULT nextval('public.datasets_id_seq'::regclass);


--
-- Name: datasets_revisions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.datasets_revisions ALTER COLUMN id SET DEFAULT nextval('public.datasets_revisions_id_seq'::regclass);


--
-- Name: delayed_jobs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.delayed_jobs ALTER COLUMN id SET DEFAULT nextval('public.delayed_jobs_id_seq'::regclass);


--
-- Name: device_descriptions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_descriptions ALTER COLUMN id SET DEFAULT nextval('public.device_descriptions_id_seq'::regclass);


--
-- Name: device_metadata id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_metadata ALTER COLUMN id SET DEFAULT nextval('public.device_metadata_id_seq'::regclass);


--
-- Name: devices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.devices ALTER COLUMN id SET DEFAULT nextval('public.devices_id_seq'::regclass);


--
-- Name: element_klasses id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.element_klasses ALTER COLUMN id SET DEFAULT nextval('public.element_klasses_id_seq'::regclass);


--
-- Name: element_klasses_revisions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.element_klasses_revisions ALTER COLUMN id SET DEFAULT nextval('public.element_klasses_revisions_id_seq'::regclass);


--
-- Name: element_tags id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.element_tags ALTER COLUMN id SET DEFAULT nextval('public.element_tags_id_seq'::regclass);


--
-- Name: elemental_compositions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elemental_compositions ALTER COLUMN id SET DEFAULT nextval('public.elemental_compositions_id_seq'::regclass);


--
-- Name: elements id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements ALTER COLUMN id SET DEFAULT nextval('public.elements_id_seq'::regclass);


--
-- Name: elements_elements id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements_elements ALTER COLUMN id SET DEFAULT nextval('public.elements_elements_id_seq'::regclass);


--
-- Name: elements_revisions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements_revisions ALTER COLUMN id SET DEFAULT nextval('public.elements_revisions_id_seq'::regclass);


--
-- Name: elements_samples id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements_samples ALTER COLUMN id SET DEFAULT nextval('public.elements_samples_id_seq'::regclass);


--
-- Name: experiments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.experiments ALTER COLUMN id SET DEFAULT nextval('public.experiments_id_seq'::regclass);


--
-- Name: fingerprints id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fingerprints ALTER COLUMN id SET DEFAULT nextval('public.fingerprints_id_seq'::regclass);


--
-- Name: inventories id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventories ALTER COLUMN id SET DEFAULT nextval('public.inventories_id_seq'::regclass);


--
-- Name: ketcherails_amino_acids id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_amino_acids ALTER COLUMN id SET DEFAULT nextval('public.ketcherails_amino_acids_id_seq'::regclass);


--
-- Name: ketcherails_atom_abbreviations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_atom_abbreviations ALTER COLUMN id SET DEFAULT nextval('public.ketcherails_atom_abbreviations_id_seq'::regclass);


--
-- Name: ketcherails_common_templates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_common_templates ALTER COLUMN id SET DEFAULT nextval('public.ketcherails_common_templates_id_seq'::regclass);


--
-- Name: ketcherails_custom_templates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_custom_templates ALTER COLUMN id SET DEFAULT nextval('public.ketcherails_custom_templates_id_seq'::regclass);


--
-- Name: ketcherails_template_categories id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_template_categories ALTER COLUMN id SET DEFAULT nextval('public.ketcherails_template_categories_id_seq'::regclass);


--
-- Name: layer_tracks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.layer_tracks ALTER COLUMN id SET DEFAULT nextval('public.layer_tracks_id_seq'::regclass);


--
-- Name: layers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.layers ALTER COLUMN id SET DEFAULT nextval('public.layers_id_seq'::regclass);


--
-- Name: literals id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.literals ALTER COLUMN id SET DEFAULT nextval('public.literals_id_seq'::regclass);


--
-- Name: literatures id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.literatures ALTER COLUMN id SET DEFAULT nextval('public.literatures_id_seq'::regclass);


--
-- Name: matrices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.matrices ALTER COLUMN id SET DEFAULT nextval('public.matrices_id_seq'::regclass);


--
-- Name: measurements id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurements ALTER COLUMN id SET DEFAULT nextval('public.measurements_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: metadata id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadata ALTER COLUMN id SET DEFAULT nextval('public.metadata_id_seq'::regclass);


--
-- Name: molecule_names id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.molecule_names ALTER COLUMN id SET DEFAULT nextval('public.molecule_names_id_seq'::regclass);


--
-- Name: molecules id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.molecules ALTER COLUMN id SET DEFAULT nextval('public.molecules_id_seq'::regclass);


--
-- Name: nmr_sim_nmr_simulations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.nmr_sim_nmr_simulations ALTER COLUMN id SET DEFAULT nextval('public.nmr_sim_nmr_simulations_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: ols_terms id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ols_terms ALTER COLUMN id SET DEFAULT nextval('public.ols_terms_id_seq'::regclass);


--
-- Name: pg_search_documents id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pg_search_documents ALTER COLUMN id SET DEFAULT nextval('public.pg_search_documents_id_seq'::regclass);


--
-- Name: predictions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.predictions ALTER COLUMN id SET DEFAULT nextval('public.predictions_id_seq'::regclass);


--
-- Name: private_notes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.private_notes ALTER COLUMN id SET DEFAULT nextval('public.private_notes_id_seq'::regclass);


--
-- Name: profiles id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.profiles ALTER COLUMN id SET DEFAULT nextval('public.profiles_id_seq'::regclass);


--
-- Name: reactions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reactions ALTER COLUMN id SET DEFAULT nextval('public.reactions_id_seq'::regclass);


--
-- Name: reactions_samples id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reactions_samples ALTER COLUMN id SET DEFAULT nextval('public.reactions_samples_id_seq'::regclass);


--
-- Name: report_templates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.report_templates ALTER COLUMN id SET DEFAULT nextval('public.report_templates_id_seq'::regclass);


--
-- Name: reports id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reports ALTER COLUMN id SET DEFAULT nextval('public.reports_id_seq'::regclass);


--
-- Name: reports_users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reports_users ALTER COLUMN id SET DEFAULT nextval('public.reports_users_id_seq'::regclass);


--
-- Name: research_plan_metadata id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plan_metadata ALTER COLUMN id SET DEFAULT nextval('public.research_plan_metadata_id_seq'::regclass);


--
-- Name: research_plan_table_schemas id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plan_table_schemas ALTER COLUMN id SET DEFAULT nextval('public.research_plan_table_schemas_id_seq'::regclass);


--
-- Name: research_plans id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plans ALTER COLUMN id SET DEFAULT nextval('public.research_plans_id_seq'::regclass);


--
-- Name: research_plans_screens id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plans_screens ALTER COLUMN id SET DEFAULT nextval('public.research_plans_screens_id_seq'::regclass);


--
-- Name: research_plans_wellplates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plans_wellplates ALTER COLUMN id SET DEFAULT nextval('public.research_plans_wellplates_id_seq'::regclass);


--
-- Name: residues id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.residues ALTER COLUMN id SET DEFAULT nextval('public.residues_id_seq'::regclass);


--
-- Name: sample_tasks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sample_tasks ALTER COLUMN id SET DEFAULT nextval('public.sample_tasks_id_seq'::regclass);


--
-- Name: samples id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.samples ALTER COLUMN id SET DEFAULT nextval('public.samples_id_seq'::regclass);


--
-- Name: scan_results id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scan_results ALTER COLUMN id SET DEFAULT nextval('public.scan_results_id_seq'::regclass);


--
-- Name: scifinder_n_credentials id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scifinder_n_credentials ALTER COLUMN id SET DEFAULT nextval('public.scifinder_n_credentials_id_seq'::regclass);


--
-- Name: screens id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.screens ALTER COLUMN id SET DEFAULT nextval('public.screens_id_seq'::regclass);


--
-- Name: screens_wellplates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.screens_wellplates ALTER COLUMN id SET DEFAULT nextval('public.screens_wellplates_id_seq'::regclass);


--
-- Name: segment_klasses id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segment_klasses ALTER COLUMN id SET DEFAULT nextval('public.segment_klasses_id_seq'::regclass);


--
-- Name: segment_klasses_revisions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segment_klasses_revisions ALTER COLUMN id SET DEFAULT nextval('public.segment_klasses_revisions_id_seq'::regclass);


--
-- Name: segments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segments ALTER COLUMN id SET DEFAULT nextval('public.segments_id_seq'::regclass);


--
-- Name: segments_revisions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segments_revisions ALTER COLUMN id SET DEFAULT nextval('public.segments_revisions_id_seq'::regclass);


--
-- Name: subscriptions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions ALTER COLUMN id SET DEFAULT nextval('public.subscriptions_id_seq'::regclass);


--
-- Name: sync_collections_users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sync_collections_users ALTER COLUMN id SET DEFAULT nextval('public.sync_collections_users_id_seq'::regclass);


--
-- Name: text_templates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.text_templates ALTER COLUMN id SET DEFAULT nextval('public.text_templates_id_seq'::regclass);


--
-- Name: third_party_apps id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.third_party_apps ALTER COLUMN id SET DEFAULT nextval('public.third_party_apps_id_seq'::regclass);


--
-- Name: user_affiliations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_affiliations ALTER COLUMN id SET DEFAULT nextval('public.user_affiliations_id_seq'::regclass);


--
-- Name: user_labels id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_labels ALTER COLUMN id SET DEFAULT nextval('public.user_labels_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: users_admins id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users_admins ALTER COLUMN id SET DEFAULT nextval('public.users_admins_id_seq'::regclass);


--
-- Name: users_devices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users_devices ALTER COLUMN id SET DEFAULT nextval('public.users_devices_id_seq'::regclass);


--
-- Name: users_groups id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users_groups ALTER COLUMN id SET DEFAULT nextval('public.users_groups_id_seq'::regclass);


--
-- Name: vocabularies id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vocabularies ALTER COLUMN id SET DEFAULT nextval('public.vocabularies_id_seq'::regclass);


--
-- Name: wellplates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.wellplates ALTER COLUMN id SET DEFAULT nextval('public.wellplates_id_seq'::regclass);


--
-- Name: wells id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.wells ALTER COLUMN id SET DEFAULT nextval('public.wells_id_seq'::regclass);


--
-- Data for Name: affiliations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.affiliations (id, company, country, organization, department, "group", created_at, updated_at, "from", "to", domain, cat) FROM stdin;
\.


--
-- Data for Name: analyses_experiments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.analyses_experiments (id, sample_id, holder_id, status, devices_analysis_id, devices_sample_id, sample_analysis_id, solvent, experiment, priority, on_day, number_of_scans, sweep_width, "time", created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ar_internal_metadata; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ar_internal_metadata (key, value, created_at, updated_at) FROM stdin;
environment	production	2024-01-23 13:44:02.869137	2024-09-27 09:08:54.851478
\.


--
-- Data for Name: attachments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.attachments (id, attachable_id, filename, identifier, checksum, storage, created_by, created_for, version, created_at, updated_at, content_type, bucket, key, thumb, folder, attachable_type, aasm_state, filesize, attachment_data, con_state, deleted_at, log_data, created_by_type) FROM stdin;
3	\N	Supporting_information.docx	0f51d8d9-1e59-43d4-97be-636c2b3e543a	\N	local	1	1	\N	2024-01-23 13:44:02.233976	2024-01-23 13:44:02.233976	\N	\N	7fdb104e-ab44-4a86-b992-5a9703d3f493	f	\N	\N	non_jcamp	\N	{"id": "1/0f51d8d9-1e59-43d4-97be-636c2b3e543a", "storage": "store", "metadata": {"md5": "c255a111db2b80cff9eba396be7de06e", "size": 32417, "filename": "Supporting_information.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N	\N	{"h": [{"c": {"id": 3, "key": "7fdb104e-ab44-4a86-b992-5a9703d3f493", "thumb": false, "bucket": null, "folder": null, "storage": "local", "version": null, "checksum": null, "filename": "Supporting_information.docx", "filesize": null, "con_state": null, "aasm_state": "non_jcamp", "created_at": "2024-01-23T13:44:02.233976", "created_by": 1, "deleted_at": null, "identifier": "0f51d8d9-1e59-43d4-97be-636c2b3e543a", "updated_at": "2024-01-23T13:44:02.233976", "created_for": 1, "content_type": null, "attachable_id": null, "attachable_type": null, "attachment_data": "{\\"id\\": \\"1/0f51d8d9-1e59-43d4-97be-636c2b3e543a\\", \\"storage\\": \\"store\\", \\"metadata\\": {\\"md5\\": \\"c255a111db2b80cff9eba396be7de06e\\", \\"size\\": 32417, \\"filename\\": \\"Supporting_information.docx\\", \\"mime_type\\": \\"application/vnd.openxmlformats-officedocument.wordprocessingml.document\\"}}"}, "v": 1, "ts": 1706017442234}], "v": 1}	\N
4	\N	Spectra.docx	7e0def2f-c9d4-4074-91d9-b26ab5495719	\N	local	1	1	\N	2024-01-23 13:44:02.243392	2024-01-23 13:44:02.243392	\N	\N	4cf7d09d-7641-4f75-bf11-2ca69995ba3f	f	\N	\N	non_jcamp	\N	{"id": "1/7e0def2f-c9d4-4074-91d9-b26ab5495719", "storage": "store", "metadata": {"md5": "b9720669839497ede31b37dff86daf08", "size": 32379, "filename": "Spectra.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N	\N	{"h": [{"c": {"id": 4, "key": "4cf7d09d-7641-4f75-bf11-2ca69995ba3f", "thumb": false, "bucket": null, "folder": null, "storage": "local", "version": null, "checksum": null, "filename": "Spectra.docx", "filesize": null, "con_state": null, "aasm_state": "non_jcamp", "created_at": "2024-01-23T13:44:02.243392", "created_by": 1, "deleted_at": null, "identifier": "7e0def2f-c9d4-4074-91d9-b26ab5495719", "updated_at": "2024-01-23T13:44:02.243392", "created_for": 1, "content_type": null, "attachable_id": null, "attachable_type": null, "attachment_data": "{\\"id\\": \\"1/7e0def2f-c9d4-4074-91d9-b26ab5495719\\", \\"storage\\": \\"store\\", \\"metadata\\": {\\"md5\\": \\"b9720669839497ede31b37dff86daf08\\", \\"size\\": 32379, \\"filename\\": \\"Spectra.docx\\", \\"mime_type\\": \\"application/vnd.openxmlformats-officedocument.wordprocessingml.document\\"}}"}, "v": 1, "ts": 1706017442243}], "v": 1}	\N
5	\N	rxn_list.html.erb	40161613-40ff-48b9-ae0d-be5a1ec2474d	\N	local	1	1	\N	2024-01-23 13:44:02.257439	2024-01-23 13:44:02.257439	\N	\N	08cb29e1-887e-4813-9c58-6d87366952a0	f	\N	\N	non_jcamp	\N	{"id": "1/40161613-40ff-48b9-ae0d-be5a1ec2474d", "storage": "store", "metadata": {"md5": "a85bab1410123d7bd636599f664aa235", "size": 2310, "filename": "rxn_list.html.erb", "mime_type": "text/html"}}	\N	\N	{"h": [{"c": {"id": 5, "key": "08cb29e1-887e-4813-9c58-6d87366952a0", "thumb": false, "bucket": null, "folder": null, "storage": "local", "version": null, "checksum": null, "filename": "rxn_list.html.erb", "filesize": null, "con_state": null, "aasm_state": "non_jcamp", "created_at": "2024-01-23T13:44:02.257439", "created_by": 1, "deleted_at": null, "identifier": "40161613-40ff-48b9-ae0d-be5a1ec2474d", "updated_at": "2024-01-23T13:44:02.257439", "created_for": 1, "content_type": null, "attachable_id": null, "attachable_type": null, "attachment_data": "{\\"id\\": \\"1/40161613-40ff-48b9-ae0d-be5a1ec2474d\\", \\"storage\\": \\"store\\", \\"metadata\\": {\\"md5\\": \\"a85bab1410123d7bd636599f664aa235\\", \\"size\\": 2310, \\"filename\\": \\"rxn_list.html.erb\\", \\"mime_type\\": \\"text/html\\"}}"}, "v": 1, "ts": 1706017442257}], "v": 1}	\N
6	\N	Standard.docx	32ba77e7-5962-44cf-b2e5-1dda89f302a3	\N	local	1	1	\N	2024-01-23 13:44:02.298977	2024-01-23 13:44:02.298977	application/vnd.openxmlformats-officedocument.wordprocessingml.document	\N	db0add32-4336-4a3e-94f3-f19b07693ad2	f	\N	\N	non_jcamp	\N	{"id": "1/32ba77e7-5962-44cf-b2e5-1dda89f302a3", "storage": "store", "metadata": {"md5": "2595f44a2dc963d58d7e32cdc5861980", "size": 93876, "filename": "Standard.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N	\N	{"h": [{"c": {"id": 6, "key": "db0add32-4336-4a3e-94f3-f19b07693ad2", "thumb": false, "bucket": null, "folder": null, "storage": "local", "version": null, "checksum": null, "filename": "Standard.docx", "filesize": null, "con_state": null, "aasm_state": "non_jcamp", "created_at": "2024-01-23T13:44:02.298977", "created_by": 1, "deleted_at": null, "identifier": "32ba77e7-5962-44cf-b2e5-1dda89f302a3", "updated_at": "2024-01-23T13:44:02.298977", "created_for": 1, "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "attachable_id": null, "attachable_type": null, "attachment_data": "{\\"id\\": \\"1/32ba77e7-5962-44cf-b2e5-1dda89f302a3\\", \\"storage\\": \\"store\\", \\"metadata\\": {\\"md5\\": \\"2595f44a2dc963d58d7e32cdc5861980\\", \\"size\\": 93876, \\"filename\\": \\"Standard.docx\\", \\"mime_type\\": \\"application/vnd.openxmlformats-officedocument.wordprocessingml.document\\"}}"}, "v": 1, "ts": 1706017442299}], "v": 1}	\N
1	\N	Standard.docx	67e79caf-a9a2-4096-894f-5e2c571d32e2	\N	local	1	1	\N	2024-01-23 13:44:02.200237	2024-01-23 13:44:02.200237	\N	\N	21241e81-8131-42a2-8f0e-5d7a31a61054	f	\N	\N	non_jcamp	\N	{"id": "1/67e79caf-a9a2-4096-894f-5e2c571d32e2", "storage": "store", "metadata": {"md5": "2595f44a2dc963d58d7e32cdc5861980", "size": 93876, "filename": "Standard.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N	\N	{"h": [{"c": {"id": 1, "key": "21241e81-8131-42a2-8f0e-5d7a31a61054", "thumb": false, "bucket": null, "folder": null, "storage": "local", "version": null, "checksum": null, "filename": "Standard.docx", "filesize": null, "con_state": null, "aasm_state": "non_jcamp", "created_at": "2024-01-23T13:44:02.200237", "created_by": 1, "deleted_at": null, "identifier": "67e79caf-a9a2-4096-894f-5e2c571d32e2", "updated_at": "2024-01-23T13:44:02.200237", "created_for": 1, "content_type": null, "attachable_id": null, "attachable_type": null, "attachment_data": "{\\"id\\": \\"1/67e79caf-a9a2-4096-894f-5e2c571d32e2\\", \\"storage\\": \\"store\\", \\"metadata\\": {\\"md5\\": \\"2595f44a2dc963d58d7e32cdc5861980\\", \\"size\\": 93876, \\"filename\\": \\"Standard.docx\\", \\"mime_type\\": \\"application/vnd.openxmlformats-officedocument.wordprocessingml.document\\"}}"}, "v": 1, "ts": 1706017442200}], "v": 1}	\N
2	\N	Supporting_information.docx	631520ee-cd61-45db-af4f-2f4af5efb80b	\N	local	1	1	\N	2024-01-23 13:44:02.223474	2024-01-23 13:44:02.223474	\N	\N	d7ba6c50-6ed6-4415-b8f2-d0bd7b38575d	f	\N	\N	non_jcamp	\N	{"id": "1/631520ee-cd61-45db-af4f-2f4af5efb80b", "storage": "store", "metadata": {"md5": "c255a111db2b80cff9eba396be7de06e", "size": 32417, "filename": "Supporting_information.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N	\N	{"h": [{"c": {"id": 2, "key": "d7ba6c50-6ed6-4415-b8f2-d0bd7b38575d", "thumb": false, "bucket": null, "folder": null, "storage": "local", "version": null, "checksum": null, "filename": "Supporting_information.docx", "filesize": null, "con_state": null, "aasm_state": "non_jcamp", "created_at": "2024-01-23T13:44:02.223474", "created_by": 1, "deleted_at": null, "identifier": "631520ee-cd61-45db-af4f-2f4af5efb80b", "updated_at": "2024-01-23T13:44:02.223474", "created_for": 1, "content_type": null, "attachable_id": null, "attachable_type": null, "attachment_data": "{\\"id\\": \\"1/631520ee-cd61-45db-af4f-2f4af5efb80b\\", \\"storage\\": \\"store\\", \\"metadata\\": {\\"md5\\": \\"c255a111db2b80cff9eba396be7de06e\\", \\"size\\": 32417, \\"filename\\": \\"Supporting_information.docx\\", \\"mime_type\\": \\"application/vnd.openxmlformats-officedocument.wordprocessingml.document\\"}}"}, "v": 1, "ts": 1706017442223}], "v": 1}	\N
\.


--
-- Data for Name: authentication_keys; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.authentication_keys (id, token, user_id, ip, role, fqdn, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: calendar_entries; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.calendar_entries (id, title, description, start_time, end_time, kind, created_by, created_at, updated_at, eventable_type, eventable_id) FROM stdin;
\.


--
-- Data for Name: calendar_entry_notifications; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.calendar_entry_notifications (id, user_id, calendar_entry_id, status, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: cellline_materials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cellline_materials (id, name, source, cell_type, organism, tissue, disease, growth_medium, biosafety_level, variant, mutation, optimal_growth_temp, cryo_pres_medium, gender, description, deleted_at, created_at, updated_at, created_by) FROM stdin;
\.


--
-- Data for Name: cellline_samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cellline_samples (id, cellline_material_id, cellline_sample_id, amount, unit, passage, contamination, name, description, user_id, deleted_at, created_at, updated_at, short_label, ancestry) FROM stdin;
\.


--
-- Data for Name: channels; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.channels (id, subject, msg_template, channel_type, created_at, updated_at) FROM stdin;
1	System Upgrade	\N	9	2024-01-23 13:44:00.299213	2024-01-23 13:44:00.299213
2	System Notification	\N	9	2024-01-23 13:44:00.302391	2024-01-23 13:44:00.302391
3	System Maintenance	\N	9	2024-01-23 13:44:00.304971	2024-01-23 13:44:00.304971
8	Send Individual Users	\N	8	2024-01-23 13:44:00.343494	2024-01-23 13:44:00.343494
14	Collection Import and Export	{"data": "Collection %{operation}: %{col_labels} processed successfully. %{expires_at}", "level": "success", "action": "CollectionActions.fetchUnsharedCollectionRoots"}	8	2024-01-23 13:44:00.565768	2024-01-23 13:44:02.363346
23	Import Samples Completed	{"data": "%{message}", "action": "CollectionActions.fetchUnsharedCollectionRoots"}	8	2024-01-23 13:44:02.712829	2024-01-23 13:44:02.71434
18	New comment on synchronized collection	{"data": "%<commented_by>s has made a new comment on %<element_type>s, %<element_name>s", "action": "CollectionActions.fetchSyncInCollectionRoots"}	8	2024-01-23 13:44:02.449573	2024-01-23 13:44:02.720794
19	Comment resolved in synchronized collection	{"data": "%<resolved_by>s has marked your comment as resolved on %<element_type>s, %<element_name>s", "action": "CollectionActions.fetchSyncInCollectionRoots"}	8	2024-01-23 13:44:02.452294	2024-01-23 13:44:02.723486
17	Assign Inbox Attachment to Sample	{"data": "This file [%{filename}] has been moved to the sample[%{info}] successfully."}	8	2024-01-23 13:44:02.143073	2024-01-23 13:44:02.143073
4	Shared Collection With Me	{"data": "%{shared_by} has shared a collection with you.", "action": "CollectionActions.fetchRemoteCollectionRoots"}	8	2024-01-23 13:44:00.30749	2024-01-23 13:44:02.338622
5	Synchronized Collection With Me	{"data": "%{synchronized_by} has synchronized a collection: %{collection_name} with you.", "action": "CollectionActions.fetchSyncInCollectionRoots"}	8	2024-01-23 13:44:00.310326	2024-01-23 13:44:02.34048
6	Inbox Arrivals To Me	{"data": "%{device_name}: new files have arrived.", "action": "InboxActions.fetchInbox"}	8	2024-01-23 13:44:00.331449	2024-01-23 13:44:02.342271
7	Report Generator Notification	{"data": "%{report_name} is ready for download!", "action": "ReportActions.updateProcessQueue", "report_id": 0}	8	2024-01-23 13:44:00.337365	2024-01-23 13:44:02.344036
9	EditorCallback	{"data": "%{filename}: has been updated.", "level": "success", "action": "ElementActions.fetchResearchPlanById", "attach_id": 0, "research_plan_id": 0}	8	2024-01-23 13:44:00.435352	2024-01-23 13:44:02.34576
10	Import Notification	{"data": "%<data>", "level": "info", "action": "CollectionActions.fetchUnsharedCollectionRoots"}	8	2024-01-23 13:44:00.441252	2024-01-23 13:44:02.347573
11	Collection Take Ownership	{"data": "%{new_owner} has taken ownership of collection: %{collection_name}.", "level": "info", "action": "CollectionActions.fetchUnsharedCollectionRoots"}	8	2024-01-23 13:44:00.447504	2024-01-23 13:44:02.349289
12	Computed Prop Notification	{"data": "Calculation for Sample %{sample_id} has %{status}", "cprop": {}, "action": "ElementActions.refreshComputedProp"}	8	2024-01-23 13:44:00.460753	2024-01-23 13:44:02.351262
15	Collection Import and Export Failure	{"data": "Collection %{operation}: There was an issue while processing %{col_labels}.", "level": "error", "action": "CollectionActions.fetchUnsharedCollectionRoots"}	8	2024-01-23 13:44:00.570786	2024-01-23 13:44:02.365108
16	Chem Spectra Notification	{"data": "%{msg}"}	8	2024-01-23 13:44:01.904279	2024-01-23 13:44:02.366625
20	Download Analyses	{"data": "Download analyses of sample: %{sample_name} processed successfully. %{expires_at}", "level": "success"}	8	2024-01-23 13:44:02.47264	2024-01-23 13:44:02.475025
21	Download Analyses Failure	{"data": " There was an issue while downloading the analyses of sample: %{sample_name}", "level": "error"}	8	2024-01-23 13:44:02.478337	2024-01-23 13:44:02.479897
22	Calender Entry Notification	{"data": "%{creator_name} %{type} calendar entry %{kind}: %{range} %{title}.", "action": "CalendarActions.navigateToElement", "eventable_id": "%{eventable_id}", "eventable_type": "%{eventable_type}"}	8	2024-01-23 13:44:02.601837	2024-01-23 13:44:02.601837
13	Gate Transfer Completed	{"data": "Data tranfer from your collection  to Chemotion-Repository: %{comment}", "level": "success", "action": "RefreshChemotionCollection"}	8	2024-01-23 13:44:00.467171	2024-01-23 13:44:02.361389
24	Send TPA attachment arrival notification	{"data": "Attachment from the third party app %{app} is available.", "level": "info"}	8	2024-11-20 06:08:46.021333	2024-11-20 06:08:46.021333
\.


--
-- Data for Name: chemicals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.chemicals (id, sample_id, cas, chemical_data, updated_at, deleted_at, log_data) FROM stdin;
\.


--
-- Data for Name: code_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.code_logs (id, source, source_id, value, deleted_at, created_at, updated_at) FROM stdin;
49f22e6b-7d35-4e19-9886-2765ff255a4d	sample	1	0098291121039069512124058409466490870349	\N	2024-01-23 15:17:46.427219	2024-01-23 15:17:46.430472
acf04140-760f-4cda-a6a2-801dbf2558ad	sample	2	0229874689984818255021260440176014219437	\N	2024-11-20 06:11:55.314743	2024-11-20 06:11:55.31601
3124ae36-9373-4d95-a313-cdc517f89089	sample	3	0065322627943593632023370058196858736777	\N	2024-11-20 06:12:56.649028	2024-11-20 06:12:56.650318
3c5bddac-98b6-4648-a19b-b5480a62bc92	sample	4	0080230674848250059058533244935602355346	\N	2024-11-20 06:14:15.811411	2024-11-20 06:14:15.812051
0e32eaea-1345-430c-8a49-3d81d8f6b073	reaction	1	0018873571413116794128852834354474692723	\N	2024-11-20 06:14:26.381509	2024-11-20 06:14:26.383295
b48e91d8-a420-4456-8b4a-3053dcf0ac35	reaction	2	0240001303508666985173550966621787434037	\N	2025-11-13 04:54:36.233837	2025-11-13 04:54:36.236614
ced018ed-bc9c-4733-84a3-d90170c786b7	sample	5	0274901470491545027998291490068106806967	\N	2025-11-13 04:54:36.618476	2025-11-13 04:54:36.620075
1c1b5554-2c6c-483e-b49d-07beebfa778f	sample	6	0037360306570888291965224343636750792591	\N	2025-11-13 04:54:36.795293	2025-11-13 04:54:36.796652
\.


--
-- Data for Name: collections; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections (id, user_id, ancestry, label, shared_by_id, is_shared, permission_level, sample_detail_level, reaction_detail_level, wellplate_detail_level, created_at, updated_at, "position", screen_detail_level, is_locked, deleted_at, is_synchronized, researchplan_detail_level, element_detail_level, tabs_segment, celllinesample_detail_level, inventory_id, devicedescription_detail_level) FROM stdin;
1	2	\N	chemotion-repository.net	\N	f	0	10	10	10	2024-01-23 15:12:02.256553	2024-01-23 15:12:02.256553	1	10	t	\N	f	10	10	{}	10	\N	10
3	3	\N	All	\N	f	0	10	10	10	2024-01-23 15:12:19.921883	2024-01-23 15:12:19.921883	0	10	t	\N	f	10	10	{}	10	\N	10
5	4	\N	All	\N	f	0	10	10	10	2024-01-24 07:01:45.778925	2024-01-24 07:01:45.778925	0	10	t	\N	f	10	10	{}	10	\N	10
4	2	\N	TEST 1	\N	f	0	10	10	10	2024-01-23 15:17:02.666049	2024-01-24 08:41:10.845282	1	10	f	\N	f	10	10	{"sample": {"results": 5, "analyses": 2, "properties": 1, "references": 4, "qc_curation": 3, "measurements": -1}}	10	\N	10
2	2	\N	All	\N	f	0	10	10	10	2024-01-23 15:12:02.26009	2024-01-25 10:10:02.777475	0	10	t	\N	f	10	10	{"try": {"TrySeg1": 2, "analyses": 3, "properties": 1, "attachments": 4}, "sample": {"results": 5, "analyses": 1, "properties": 3, "references": 4, "qc_curation": 2, "measurements": -1}}	10	\N	10
6	5	\N	All	\N	f	0	10	10	10	2024-02-16 08:50:38.511259	2024-02-16 08:50:38.511259	0	10	t	\N	f	10	10	{}	10	\N	10
7	6	\N	All	\N	f	0	10	10	10	2024-02-16 08:51:22.298693	2024-02-16 08:51:22.298693	0	10	t	\N	f	10	10	{}	10	\N	10
8	7	\N	chemotion-repository.net	\N	f	0	10	10	10	2024-02-16 08:52:48.558915	2024-02-16 08:52:48.558915	1	10	t	\N	f	10	10	{}	10	\N	10
9	7	\N	All	\N	f	0	10	10	10	2024-02-16 08:52:48.561313	2024-02-16 08:52:48.561313	0	10	t	\N	f	10	10	{}	10	\N	10
10	8	\N	All	\N	f	0	10	10	10	2024-02-16 08:53:15.379007	2024-02-16 08:53:15.379007	0	10	t	\N	f	10	10	{}	10	\N	10
11	7	\N	FIXED	\N	f	0	10	10	10	2024-03-21 10:31:23.524241	2024-03-21 10:40:57.388683	1	10	f	\N	f	10	10	{}	10	\N	10
12	9	\N	chemotion-repository.net	\N	f	0	10	10	10	2024-09-27 09:11:56.595124	2024-09-27 09:11:56.595124	1	10	t	\N	f	10	10	{}	10	\N	10
13	9	\N	All	\N	f	0	10	10	10	2024-09-27 09:11:56.596278	2024-09-27 09:11:56.596278	0	10	t	\N	f	10	10	{}	10	\N	10
\.


--
-- Data for Name: collections_celllines; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_celllines (id, collection_id, cellline_sample_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: collections_device_descriptions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_device_descriptions (id, collection_id, device_description_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: collections_elements; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_elements (id, collection_id, element_id, element_type, deleted_at) FROM stdin;
5	11	3	\N	\N
6	9	3	\N	\N
7	11	4	\N	\N
8	9	4	\N	\N
9	11	5	\N	\N
10	9	5	\N	\N
1	4	1	\N	2024-12-04 12:57:28.631002
2	2	1	\N	2024-12-04 12:57:28.631824
3	4	2	\N	2024-12-04 12:57:28.674548
4	2	2	\N	2024-12-04 12:57:28.67503
\.


--
-- Data for Name: collections_reactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_reactions (id, collection_id, reaction_id, deleted_at) FROM stdin;
1	11	1	\N
2	9	1	\N
3	11	2	\N
4	9	2	\N
\.


--
-- Data for Name: collections_research_plans; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_research_plans (id, collection_id, research_plan_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: collections_samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_samples (id, collection_id, sample_id, deleted_at) FROM stdin;
1	4	1	\N
2	2	1	\N
3	11	2	\N
4	9	2	\N
5	11	3	\N
6	9	3	\N
7	11	4	\N
8	9	4	\N
9	9	5	\N
10	11	5	\N
11	9	6	\N
12	11	6	\N
\.


--
-- Data for Name: collections_screens; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_screens (id, collection_id, screen_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: collections_vessels; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_vessels (id, collection_id, vessel_id, created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: collections_wellplates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_wellplates (id, collection_id, wellplate_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: collector_errors; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collector_errors (id, error_code, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: comments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.comments (id, content, created_by, section, status, submitter, resolver_name, commentable_id, commentable_type, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: computed_props; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.computed_props (id, molecule_id, max_potential, min_potential, mean_potential, lumo, homo, ip, ea, dipol_debye, status, data, created_at, updated_at, mean_abs_potential, creator, sample_id, tddft, task_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: container_hierarchies; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.container_hierarchies (ancestor_id, descendant_id, generations) FROM stdin;
1	1	0
2	2	0
3	3	0
2	3	1
4	4	0
5	5	0
4	5	1
6	6	0
7	7	0
6	7	1
8	8	0
9	9	0
10	10	0
9	10	1
11	11	0
12	12	0
11	12	1
13	13	0
14	14	0
13	14	1
15	15	0
16	16	0
15	16	1
17	17	0
18	18	0
17	18	1
19	19	0
20	20	0
19	20	1
21	21	0
22	22	0
21	22	1
23	23	0
24	24	0
23	24	1
25	25	0
26	26	0
25	26	1
27	27	0
28	28	0
27	28	1
29	29	0
30	30	0
29	30	1
\.


--
-- Data for Name: containers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.containers (id, ancestry, containable_id, containable_type, name, container_type, description, extended_metadata, created_at, updated_at, parent_id, plain_text_content, deleted_at, log_data) FROM stdin;
1	\N	2	User	inbox	root	\N		2024-01-23 15:16:40.246973	2024-01-23 15:16:40.273554	\N	\N	\N	{"h": [{"c": {"id": 1, "name": "inbox", "ancestry": null, "parent_id": null, "created_at": "2024-01-23T15:16:40.246973", "deleted_at": null, "updated_at": "2024-01-23T15:16:40.273554", "description": null, "containable_id": 2, "container_type": "root", "containable_type": "User", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1706023000274}], "v": 1}
3	\N	\N	\N	new	analyses		"report"=>"true"	2024-01-23 15:17:46.337888	2024-01-23 15:17:46.337888	2	\N	\N	{"h": [{"c": {"id": 3, "name": "new", "ancestry": null, "parent_id": 2, "created_at": "2024-01-23T15:17:46.337888", "deleted_at": null, "updated_at": "2024-01-23T15:17:46.337888", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "v": 1, "ts": 1706023066338}], "v": 1}
2	\N	1	Sample	\N	\N	\N		2024-01-23 15:17:46.323082	2024-01-23 15:17:46.441102	\N	\N	\N	{"h": [{"c": {"id": 2, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-01-23T15:17:46.323082", "deleted_at": null, "updated_at": "2024-01-23T15:17:46.441102", "description": null, "containable_id": 1, "container_type": null, "containable_type": "Sample", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1706023066441}], "v": 1}
5	\N	\N	\N	new	analyses		"report"=>"true"	2024-01-24 08:17:12.606606	2024-01-24 08:17:12.606606	4	\N	\N	{"h": [{"c": {"id": 5, "name": "new", "ancestry": null, "parent_id": 4, "created_at": "2024-01-24T08:17:12.606606", "deleted_at": null, "updated_at": "2024-01-24T08:17:12.606606", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "v": 1, "ts": 1706084232607}], "v": 1}
4	\N	1	Labimotion::Element	\N	\N	\N		2024-01-24 08:17:12.591497	2024-01-24 08:17:12.627644	\N	\N	\N	{"h": [{"c": {"id": 4, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-01-24T08:17:12.591497", "deleted_at": null, "updated_at": "2024-01-24T08:17:12.627644", "description": null, "containable_id": 1, "container_type": null, "containable_type": "Labimotion::Element", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1706084232628}], "v": 1}
7	\N	\N	\N	new	analyses		"report"=>"true"	2024-02-16 08:49:01.378426	2024-02-16 08:49:01.378426	6	\N	\N	{"h": [{"c": {"id": 7, "name": "new", "ancestry": null, "parent_id": 6, "created_at": "2024-02-16T08:49:01.378426", "deleted_at": null, "updated_at": "2024-02-16T08:49:01.378426", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "v": 1, "ts": 1708073341378}], "v": 1}
6	\N	2	Labimotion::Element	\N	\N			2024-02-16 08:49:01.352578	2024-02-16 08:49:01.398714	\N	\N	\N	{"h": [{"c": {"id": 6, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-02-16T08:49:01.352578", "deleted_at": null, "updated_at": "2024-02-16T08:49:01.398714", "description": "", "containable_id": 2, "container_type": null, "containable_type": "Labimotion::Element", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1708073341399}], "v": 1}
8	\N	7	User	inbox	root	\N		2024-02-16 09:48:37.45738	2024-02-16 09:48:37.480074	\N	\N	\N	{"h": [{"c": {"id": 8, "name": "inbox", "ancestry": null, "parent_id": null, "created_at": "2024-02-16T09:48:37.45738", "deleted_at": null, "updated_at": "2024-02-16T09:48:37.480074", "description": null, "containable_id": 7, "container_type": "root", "containable_type": "User", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1708076917480}], "v": 1}
10	\N	\N	\N	new	analyses		"report"=>"true"	2024-03-21 10:32:02.11686	2024-03-21 10:32:02.11686	9	\N	\N	{"h": [{"c": {"id": 10, "name": "new", "ancestry": null, "parent_id": 9, "created_at": "2024-03-21T10:32:02.11686", "deleted_at": null, "updated_at": "2024-03-21T10:32:02.11686", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "v": 1, "ts": 1711017122117}], "v": 1}
9	\N	3	Labimotion::Element	\N	\N			2024-03-21 10:32:02.092653	2024-03-21 10:32:02.138395	\N	\N	\N	{"h": [{"c": {"id": 9, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-03-21T10:32:02.092653", "deleted_at": null, "updated_at": "2024-03-21T10:32:02.138395", "description": "", "containable_id": 3, "container_type": null, "containable_type": "Labimotion::Element", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1711017122138}], "v": 1}
12	\N	\N	\N	new	analyses		"report"=>"true"	2024-03-21 10:41:42.596332	2024-03-21 10:41:42.596332	11	\N	\N	{"h": [{"c": {"id": 12, "name": "new", "ancestry": null, "parent_id": 11, "created_at": "2024-03-21T10:41:42.596332", "deleted_at": null, "updated_at": "2024-03-21T10:41:42.596332", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "v": 1, "ts": 1711017702596}], "v": 1}
11	\N	4	Labimotion::Element	\N	\N			2024-03-21 10:41:42.572604	2024-03-21 10:41:42.617244	\N	\N	\N	{"h": [{"c": {"id": 11, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-03-21T10:41:42.572604", "deleted_at": null, "updated_at": "2024-03-21T10:41:42.617244", "description": "", "containable_id": 4, "container_type": null, "containable_type": "Labimotion::Element", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1711017702617}], "v": 1}
14	\N	\N	\N	new	analyses		"report"=>"true"	2024-03-21 12:13:25.314721	2024-03-21 12:13:25.314721	13	\N	\N	{"h": [{"c": {"id": 14, "name": "new", "ancestry": null, "parent_id": 13, "created_at": "2024-03-21T12:13:25.314721", "deleted_at": null, "updated_at": "2024-03-21T12:13:25.314721", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "v": 1, "ts": 1711023205315}], "v": 1}
13	\N	5	Labimotion::Element	\N	\N			2024-03-21 12:13:25.292371	2024-03-21 12:13:25.333296	\N	\N	\N	{"h": [{"c": {"id": 13, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-03-21T12:13:25.292371", "deleted_at": null, "updated_at": "2024-03-21T12:13:25.333296", "description": "", "containable_id": 5, "container_type": null, "containable_type": "Labimotion::Element", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1711023205333}], "v": 1}
15	\N	2	Sample	\N	\N			2024-11-20 06:11:55.274029	2024-11-20 06:11:55.320363	\N	\N	\N	{"h": [{"c": {"id": 15, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-11-20T06:11:55.274029", "deleted_at": null, "updated_at": "2024-11-20T06:11:55.320363", "description": "", "containable_id": 2, "container_type": null, "containable_type": "Sample", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1732083115320}], "v": 1}
17	\N	3	Sample	\N	\N			2024-11-20 06:12:56.606384	2024-11-20 06:12:56.654722	\N	\N	\N	{"h": [{"c": {"id": 17, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-11-20T06:12:56.606384", "deleted_at": null, "updated_at": "2024-11-20T06:12:56.654722", "description": "", "containable_id": 3, "container_type": null, "containable_type": "Sample", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1732083176655}], "v": 1}
19	\N	4	Sample	\N	\N			2024-11-20 06:14:15.765622	2024-11-20 06:14:15.815153	\N	\N	\N	{"h": [{"c": {"id": 19, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-11-20T06:14:15.765622", "deleted_at": null, "updated_at": "2024-11-20T06:14:15.815153", "description": "", "containable_id": 4, "container_type": null, "containable_type": "Sample", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1732083255815}], "v": 1}
21	\N	1	Reaction	\N	\N			2024-11-20 06:14:26.398815	2024-11-20 06:14:26.414076	\N	\N	\N	{"h": [{"c": {"id": 21, "name": null, "ancestry": null, "parent_id": null, "created_at": "2024-11-20T06:14:26.398815", "deleted_at": null, "updated_at": "2024-11-20T06:14:26.414076", "description": "", "containable_id": 1, "container_type": null, "containable_type": "Reaction", "extended_metadata": "{}", "plain_text_content": null}, "v": 1, "ts": 1732083266414}], "v": 1}
16	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:11:55.286131	2024-11-20 06:14:26.436514	15	\N	\N	{"h": [{"c": {"id": 16, "name": "new", "ancestry": null, "parent_id": 15, "created_at": "2024-11-20T06:11:55.286131", "deleted_at": null, "updated_at": "2024-11-20T06:14:26.436514", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"kind\\": null, \\"index\\": null, \\"report\\": \\"true\\", \\"status\\": null, \\"instrument\\": null}", "plain_text_content": null}, "v": 1, "ts": 1732083266437}], "v": 1}
18	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:12:56.627518	2024-11-20 06:14:26.462635	17	\N	\N	{"h": [{"c": {"id": 18, "name": "new", "ancestry": null, "parent_id": 17, "created_at": "2024-11-20T06:12:56.627518", "deleted_at": null, "updated_at": "2024-11-20T06:14:26.462635", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"kind\\": null, \\"index\\": null, \\"report\\": \\"true\\", \\"status\\": null, \\"instrument\\": null}", "plain_text_content": null}, "v": 1, "ts": 1732083266463}], "v": 1}
20	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:14:15.783372	2024-11-20 06:14:26.488333	19	\N	\N	{"h": [{"c": {"id": 20, "name": "new", "ancestry": null, "parent_id": 19, "created_at": "2024-11-20T06:14:15.783372", "deleted_at": null, "updated_at": "2024-11-20T06:14:26.488333", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"kind\\": null, \\"index\\": null, \\"report\\": \\"true\\", \\"status\\": null, \\"instrument\\": null}", "plain_text_content": null}, "v": 1, "ts": 1732083266488}], "v": 1}
22	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:14:26.408483	2024-11-20 06:15:17.636943	21	\N	\N	{"h": [{"c": {"id": 22, "name": "new", "ancestry": null, "parent_id": 21, "created_at": "2024-11-20T06:14:26.408483", "deleted_at": null, "updated_at": "2024-11-20T06:15:17.636943", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"kind\\": null, \\"index\\": null, \\"report\\": \\"true\\", \\"status\\": null, \\"instrument\\": null}", "plain_text_content": null}, "v": 1, "ts": 1732083317637}], "v": 1}
26	\N	\N	\N	\N	analyses	\N		2025-11-13 04:54:36.414552	2025-11-13 04:54:36.414552	25	\N	\N	{"h": [{"c": {"id": 26, "name": null, "ancestry": null, "parent_id": 25, "created_at": "2025-11-13T04:54:36.414552", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.414552", "description": null, "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676415}], "v": 1}
23	\N	2	Reaction	\N	\N			2025-11-13 04:54:36.276477	2025-11-13 04:54:36.314906	\N	\N	\N	{"h": [{"c": {"id": 23, "name": null, "ancestry": null, "parent_id": null, "created_at": "2025-11-13T04:54:36.276477", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.276477", "description": null, "containable_id": null, "container_type": null, "containable_type": null, "extended_metadata": "{}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676276}, {"c": {"updated_at": "2025-11-13T04:54:36.286313", "description": ""}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 2, "ts": 1763009676286}, {"c": {"updated_at": "2025-11-13T04:54:36.314906", "containable_id": 2, "containable_type": "Reaction"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 3, "ts": 1763009676315}], "v": 3}
24	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2025-11-13 04:54:36.298266	2025-11-13 04:55:55.143951	23	\N	\N	{"h": [{"c": {"id": 24, "name": "new", "ancestry": null, "parent_id": 23, "created_at": "2025-11-13T04:54:36.298266", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.298266", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676298}, {"c": {"updated_at": "2025-11-13T04:55:55.143951", "extended_metadata": {"kind": null, "index": null, "status": null, "instrument": null}}, "m": {"_r": 7, "uuid": "ffd31cb0-d827-412a-aec9-a3cd099d2db5"}, "v": 2, "ts": 1763009755144}], "v": 2}
30	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2025-11-13 04:54:36.751172	2025-11-13 04:55:55.306959	29	\N	\N	{"h": [{"c": {"id": 30, "name": "new", "ancestry": null, "parent_id": 29, "created_at": "2025-11-13T04:54:36.751172", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.751172", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676751}, {"c": {"updated_at": "2025-11-13T04:55:55.306959", "extended_metadata": {"kind": null, "index": null, "status": null, "instrument": null}}, "m": {"_r": 7, "uuid": "ffd31cb0-d827-412a-aec9-a3cd099d2db5"}, "v": 2, "ts": 1763009755307}], "v": 2}
25	\N	\N	\N	root	root	\N		2025-11-13 04:54:36.40571	2025-11-13 04:54:36.693414	\N	\N	\N	{"h": [{"c": {"id": 25, "name": "root", "ancestry": null, "parent_id": null, "created_at": "2025-11-13T04:54:36.40571", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.40571", "description": null, "containable_id": null, "container_type": "root", "containable_type": null, "extended_metadata": "{}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676406}, {"c": {"updated_at": "2025-11-13T04:54:36.628074", "containable_id": 5, "containable_type": "Sample"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 2, "ts": 1763009676628}, {"c": {"updated_at": "2025-11-13T04:54:36.693414", "containable_id": null, "containable_type": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 3, "ts": 1763009676693}], "v": 3}
27	\N	5	Sample	\N	\N			2025-11-13 04:54:36.665091	2025-11-13 04:54:36.696295	\N	\N	\N	{"h": [{"c": {"id": 27, "name": null, "ancestry": null, "parent_id": null, "created_at": "2025-11-13T04:54:36.665091", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.665091", "description": null, "containable_id": null, "container_type": null, "containable_type": null, "extended_metadata": "{}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676665}, {"c": {"updated_at": "2025-11-13T04:54:36.674072", "description": ""}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 2, "ts": 1763009676674}, {"c": {"updated_at": "2025-11-13T04:54:36.696295", "containable_id": 5, "containable_type": "Sample"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 3, "ts": 1763009676696}], "v": 3}
29	\N	6	Sample	\N	\N			2025-11-13 04:54:36.736182	2025-11-13 04:54:36.80313	\N	\N	\N	{"h": [{"c": {"id": 29, "name": null, "ancestry": null, "parent_id": null, "created_at": "2025-11-13T04:54:36.736182", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.736182", "description": null, "containable_id": null, "container_type": null, "containable_type": null, "extended_metadata": "{}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676736}, {"c": {"updated_at": "2025-11-13T04:54:36.743895", "description": ""}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 2, "ts": 1763009676744}, {"c": {"updated_at": "2025-11-13T04:54:36.80313", "containable_id": 6, "containable_type": "Sample"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 3, "ts": 1763009676803}], "v": 3}
28	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2025-11-13 04:54:36.682076	2025-11-13 04:55:55.238837	27	\N	\N	{"h": [{"c": {"id": 28, "name": "new", "ancestry": null, "parent_id": 27, "created_at": "2025-11-13T04:54:36.682076", "deleted_at": null, "updated_at": "2025-11-13T04:54:36.682076", "description": "", "containable_id": null, "container_type": "analyses", "containable_type": null, "extended_metadata": "{\\"report\\": \\"true\\"}", "plain_text_content": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676682}, {"c": {"updated_at": "2025-11-13T04:55:55.238837", "extended_metadata": {"kind": null, "index": null, "status": null, "instrument": null}}, "m": {"_r": 7, "uuid": "ffd31cb0-d827-412a-aec9-a3cd099d2db5"}, "v": 2, "ts": 1763009755239}], "v": 2}
\.


--
-- Data for Name: dataset_klasses; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.dataset_klasses (id, ols_term_id, label, "desc", properties_template, is_active, place, created_by, created_at, updated_at, deleted_at, uuid, properties_release, released_at, identifier, sync_time, updated_by, released_by, sync_by, admin_ids, user_ids, version) FROM stdin;
1	CHMO:0000593	1H nuclear magnetic resonance spectroscopy (1H NMR)	1H nuclear magnetic resonance spectroscopy (1H NMR)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "e9f21b78-3de7-41c1-8e55-9f38e456e454", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	10	1	2024-01-23 13:44:01.428993	2024-01-23 13:44:01.822835	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
2	CHMO:0000595	13C nuclear magnetic resonance spectroscopy (13C NMR)	13C nuclear magnetic resonance spectroscopy (13C NMR)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "2f981b93-2a16-417f-b255-01621fb7e3e0", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	20	1	2024-01-23 13:44:01.435117	2024-01-23 13:44:01.839669	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
3	CHMO:0000470	mass spectrometry (MS)	mass spectrometry (MS)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "62cc2f01-a1a6-4a06-bb93-d48f44dcf263", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	30	1	2024-01-23 13:44:01.440317	2024-01-23 13:44:01.846564	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
4	CHMO:0001075	elemental analysis (EA)	elemental analysis (EA)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "332651a1-4eda-4848-bcde-fed1f36cc165", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	40	1	2024-01-23 13:44:01.444747	2024-01-23 13:44:01.852804	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
5	CHMO:0000497	gas chromatography-mass spectrometry (GCMS)	gas chromatography-mass spectrometry (GCMS)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "417474b8-f962-43c4-b9cc-00528d5be970", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	50	1	2024-01-23 13:44:01.44912	2024-01-23 13:44:01.867143	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
6	CHMO:0001009	high-performance liquid chromatography (HPLC)	high-performance liquid chromatography (HPLC)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "86ddc873-4c35-4258-94cb-571d52a39183", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	60	1	2024-01-23 13:44:01.453548	2024-01-23 13:44:01.873555	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
7	CHMO:0000630	infrared absorption spectroscopy (IR)	infrared absorption spectroscopy (IR)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "24bd888e-6fc2-4465-b17e-897705ede07e", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	70	1	2024-01-23 13:44:01.457933	2024-01-23 13:44:01.878864	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
8	CHMO:0001007	thin-layer chromatography (TLC)	thin-layer chromatography (TLC)	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "9a9665e0-a38b-4f0f-9358-56b72a4056d1", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	f	80	1	2024-01-23 13:44:01.462131	2024-01-23 13:44:01.884963	\N	\N	{}	\N	\N	\N	\N	\N	\N	{}	{}	\N
\.


--
-- Data for Name: dataset_klasses_revisions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.dataset_klasses_revisions (id, dataset_klass_id, uuid, properties_release, released_at, released_by, created_by, created_at, updated_at, deleted_at, version) FROM stdin;
1	1	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "e9f21b78-3de7-41c1-8e55-9f38e456e454", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.836659	2024-01-23 13:44:01.836659	\N	\N
2	2	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "2f981b93-2a16-417f-b255-01621fb7e3e0", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.844229	2024-01-23 13:44:01.844229	\N	\N
3	3	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "62cc2f01-a1a6-4a06-bb93-d48f44dcf263", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.850646	2024-01-23 13:44:01.850646	\N	\N
4	4	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "332651a1-4eda-4848-bcde-fed1f36cc165", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.85653	2024-01-23 13:44:01.85653	\N	\N
5	5	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "417474b8-f962-43c4-b9cc-00528d5be970", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.871491	2024-01-23 13:44:01.871491	\N	\N
6	6	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "86ddc873-4c35-4258-94cb-571d52a39183", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.87681	2024-01-23 13:44:01.87681	\N	\N
7	7	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "24bd888e-6fc2-4465-b17e-897705ede07e", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.882792	2024-01-23 13:44:01.882792	\N	\N
8	8	\N	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "9a9665e0-a38b-4f0f-9358-56b72a4056d1", "klass": "DatasetKlass", "layers": {}, "select_options": {}}	\N	\N	\N	2024-01-23 13:44:01.888635	2024-01-23 13:44:01.888635	\N	\N
\.


--
-- Data for Name: datasets; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.datasets (id, dataset_klass_id, element_type, element_id, properties, created_at, updated_at, uuid, klass_uuid, deleted_at, properties_release) FROM stdin;
\.


--
-- Data for Name: datasets_revisions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.datasets_revisions (id, dataset_id, uuid, klass_uuid, properties, created_by, created_at, updated_at, deleted_at, properties_release) FROM stdin;
\.


--
-- Data for Name: delayed_jobs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.delayed_jobs (id, priority, attempts, handler, last_error, run_at, locked_at, failed_at, locked_by, queue, created_at, updated_at, cron) FROM stdin;
152	0	0	--- !ruby/object:ActiveJob::QueueAdapters::DelayedJobAdapter::JobWrapper\njob_data:\n  job_class: PubchemCidJob\n  job_id: 9a3b4a95-edf9-4970-8674-027caa7bcb72\n  provider_job_id: \n  queue_name: pubchem\n  priority: \n  arguments: []\n  executions: 0\n  exception_executions: {}\n  locale: en\n  timezone: UTC\n  enqueued_at: '2025-11-13T04:54:01Z'\n	\N	2025-11-16 13:02:00	\N	\N	\N	pubchem	2025-11-13 04:54:01.68817	2025-11-13 04:54:01.68817	2 13 * * 7
153	0	0	--- !ruby/object:ActiveJob::QueueAdapters::DelayedJobAdapter::JobWrapper\njob_data:\n  job_class: PubchemLcssJob\n  job_id: 34d66231-3001-4626-a2f9-3afab94676ea\n  provider_job_id: \n  queue_name: pubchemLcss\n  priority: \n  arguments: []\n  executions: 0\n  exception_executions: {}\n  locale: en\n  timezone: UTC\n  enqueued_at: '2025-11-13T04:54:01Z'\n	\N	2025-11-16 09:32:00	\N	\N	\N	pubchemLcss	2025-11-13 04:54:01.697851	2025-11-13 04:54:01.697851	32 9 * * 7
154	0	0	--- !ruby/object:ActiveJob::QueueAdapters::DelayedJobAdapter::JobWrapper\njob_data:\n  job_class: RefreshElementTagJob\n  job_id: 7cfb6ec4-b378-4c7e-86ad-73f48ff74469\n  provider_job_id: \n  queue_name: refresh_element_tag\n  priority: \n  arguments: []\n  executions: 0\n  exception_executions: {}\n  locale: en\n  timezone: UTC\n  enqueued_at: '2025-11-13T04:54:01Z'\n	\N	2025-11-15 18:04:00	\N	\N	\N	refresh_element_tag	2025-11-13 04:54:01.704293	2025-11-13 04:54:01.704293	4 18 * * 6
155	0	0	--- !ruby/object:ActiveJob::QueueAdapters::DelayedJobAdapter::JobWrapper\njob_data:\n  job_class: DiskUsageJob\n  job_id: bd8c3f8f-81c8-4a18-8b6c-1c3aee2d0a75\n  provider_job_id: \n  queue_name: disk_usage\n  priority: \n  arguments: []\n  executions: 0\n  exception_executions: {}\n  locale: en\n  timezone: UTC\n  enqueued_at: '2025-11-13T04:54:01Z'\n	\N	2025-11-15 01:00:00	\N	\N	\N	disk_usage	2025-11-13 04:54:01.710421	2025-11-13 04:54:01.710421	0 1 * * 6
\.


--
-- Data for Name: device_descriptions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.device_descriptions (id, access_comments, access_options, ancestry, application_name, application_version, building, contact_for_maintenance, consumables_needed_for_maintenance, created_by, deleted_at, description, description_for_methods_part, device_id, device_type, device_type_detail, general_tags, helpers_uploaded, infrastructure_assignment, institute, maintenance_contract_available, maintenance_scheduling, measures_after_full_shut_down, measures_after_short_shut_down, measures_to_plan_offline_period, name, operation_mode, operators, ontologies, planned_maintenance, policies_and_user_information, restart_after_planned_offline_period, room, serial_number, setup_descriptions, size, short_label, unexpected_maintenance, university_campus, vendor_id, vendor_url, version_characterization, version_doi, version_doi_url, version_identifier_type, version_installation_start_date, version_installation_end_date, version_number, weight, weight_unit, vendor_device_name, vendor_device_id, vendor_company_name, created_at, updated_at, log_data) FROM stdin;
\.


--
-- Data for Name: device_metadata; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.device_metadata (id, device_id, doi, url, landing_page, name, type, description, publisher, publication_year, manufacturers, owners, dates, created_at, updated_at, deleted_at, doi_sequence, data_cite_prefix, data_cite_created_at, data_cite_updated_at, data_cite_version, data_cite_last_response, data_cite_state, data_cite_creator_name) FROM stdin;
\.


--
-- Data for Name: devices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.devices (id, name, name_abbreviation, first_name, last_name, email, serial_number, verification_status, account_active, visibility, deleted_at, created_at, updated_at, datacollector_method, datacollector_dir, datacollector_host, datacollector_user, datacollector_authentication, datacollector_number_of_files, datacollector_key_name, datacollector_user_level_selected, novnc_token, novnc_target, novnc_password) FROM stdin;
5	Test Device 1 T.D	TD	Test Device 1	T.D	td@kit.edu	\N	none	f	f	\N	2024-02-16 08:50:38.507891	2024-02-16 08:50:38.507891	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N
6	Admin Device 2 A.Device	AD	Admin Device 2	A.Device	ad@git.edu	\N	none	f	f	\N	2024-02-16 08:51:22.295244	2024-02-16 08:51:24.672829	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N
\.


--
-- Data for Name: element_klasses; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.element_klasses (id, name, label, "desc", icon_name, is_active, klass_prefix, is_generic, place, properties_template, created_by, created_at, updated_at, deleted_at, uuid, properties_release, released_at, identifier, sync_time, updated_by, released_by, sync_by, admin_ids, user_ids, version) FROM stdin;
6	research_plan	Research Plan	ELN Research Plan	icon-research_plan	t		f	5	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "194a26e0-2663-4f76-a529-2fb6e5bc0ddf", "klass": "ElementKlass", "select_options": {}}	\N	2024-01-23 13:44:01.362559	2024-01-23 13:44:01.740555	\N	194a26e0-2663-4f76-a529-2fb6e5bc0ddf	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "194a26e0-2663-4f76-a529-2fb6e5bc0ddf", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.740399	\N	\N	\N	\N	\N	{}	{}	\N
1	cell_line	Cell Line	ELN Cell Line	icon-cell_line	t		f	5	{}	\N	2024-01-23 13:44:01.336732	2024-01-23 13:44:02.859896	\N	5f59fd06-c442-4f78-abb1-765061989227	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "5f59fd06-c442-4f78-abb1-765061989227", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.703305	\N	\N	\N	\N	\N	{}	{}	\N
2	sample	Sample	ELN Sample	icon-sample	t		f	1	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "e066565a-a4a6-4933-b725-c42c92dab64d", "klass": "ElementKlass", "select_options": {}}	\N	2024-01-23 13:44:01.342669	2024-01-23 13:44:01.719032	\N	e066565a-a4a6-4933-b725-c42c92dab64d	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "e066565a-a4a6-4933-b725-c42c92dab64d", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.718844	\N	\N	\N	\N	\N	{}	{}	\N
3	reaction	Reaction	ELN Reaction	icon-reaction	t		f	2	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "900859ad-916e-4093-98c1-e8a87270ae64", "klass": "ElementKlass", "select_options": {}}	\N	2024-01-23 13:44:01.34801	2024-01-23 13:44:01.72501	\N	900859ad-916e-4093-98c1-e8a87270ae64	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "900859ad-916e-4093-98c1-e8a87270ae64", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.724862	\N	\N	\N	\N	\N	{}	{}	\N
4	wellplate	Wellplate	ELN Wellplate	icon-wellplate	t		f	3	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "85e19d00-7d22-4310-911c-ba17f234992e", "klass": "ElementKlass", "select_options": {}}	\N	2024-01-23 13:44:01.352871	2024-01-23 13:44:01.730194	\N	85e19d00-7d22-4310-911c-ba17f234992e	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "85e19d00-7d22-4310-911c-ba17f234992e", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.73005	\N	\N	\N	\N	\N	{}	{}	\N
5	screen	Screen	ELN Screen	icon-screen	t		f	4	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "6e8c7739-908b-4026-a38c-eee668384baf", "klass": "ElementKlass", "select_options": {}}	\N	2024-01-23 13:44:01.357755	2024-01-23 13:44:01.735334	\N	6e8c7739-908b-4026-a38c-eee668384baf	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "6e8c7739-908b-4026-a38c-eee668384baf", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.735182	\N	\N	\N	\N	\N	{}	{}	\N
8	wrk	Workflow		fa fa-sort-amount-asc	t	WRK	t	100	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "078843ad-4de4-40b0-bca8-136a06459f50", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}, "fixed": {"wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-1-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "1", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 153.94964022108297, "y": 271.54511305952786, "zoom": 1.316636906723931}}, "identifier": null, "select_options": {}}	7	2024-03-20 11:27:36.257767	2024-03-21 10:38:44.894667	\N	078843ad-4de4-40b0-bca8-136a06459f50	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "078843ad-4de4-40b0-bca8-136a06459f50", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}, "fixed": {"wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-1-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "1", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 153.94964022108297, "y": 271.54511305952786, "zoom": 1.316636906723931}}, "identifier": null, "select_options": {}}	2024-03-21 10:38:44.892811	\N	\N	7	7	\N	{}	{}	2.0
7	try	Tryout		fa fa-check-square	f	T	t	100	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "identifier": null, "select_options": {}}	2	2024-01-24 07:02:39.227237	2024-12-04 12:57:28.688874	2024-12-04 12:57:28.688868	8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "identifier": null, "select_options": {}}	2024-02-16 08:48:17.518249	1219ab91-45b7-4c4b-999c-96b3b864ab95	\N	2	2	\N	{}	{}	2.0
9	try	Tryout		fa fa-check-square	t	T	t	100	{"pkg": {"eln": {"version": "v1.10.2", "base_revision": "7e269bb594d29413788f3e5bfa16544981b5d392", "current_revision": "7e269bb594d29413788f3e5bfa16544981b5d392"}, "name": "chem-generic-ui", "version": "1.4.4", "labimotion": "1.4.0.2"}, "uuid": "5c136a3d-49f4-429e-a8e9-a0e7090d9956", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "748041a1-1639-424d-9147-1f5ea2436c43", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "017cd221-2419-44f1-a1b6-16411b7aa44f", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "a2c7b308-b1d5-447b-b3dd-8b090c11f4c1", "type": "label", "value": "TEST"}, {"id": "b21ffab0-8e17-4934-bb45-218ef371348d", "type": "number", "value": ""}, {"id": "087203bc-2493-4b2d-bae1-92437167ed28", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": "0e7d841f-6f2a-44e3-b2e9-b9e2a8fa6241", "select_options": {}}	7	2024-12-04 12:57:51.921336	2024-12-04 14:58:24.644875	\N	5c136a3d-49f4-429e-a8e9-a0e7090d9956	{"pkg": {"eln": {"version": "v1.10.2", "base_revision": "7e269bb594d29413788f3e5bfa16544981b5d392", "current_revision": "7e269bb594d29413788f3e5bfa16544981b5d392"}, "name": "chem-generic-ui", "version": "1.4.4", "labimotion": "1.4.0.2"}, "uuid": "5c136a3d-49f4-429e-a8e9-a0e7090d9956", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "748041a1-1639-424d-9147-1f5ea2436c43", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "017cd221-2419-44f1-a1b6-16411b7aa44f", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "a2c7b308-b1d5-447b-b3dd-8b090c11f4c1", "type": "label", "value": "TEST"}, {"id": "b21ffab0-8e17-4934-bb45-218ef371348d", "type": "number", "value": ""}, {"id": "087203bc-2493-4b2d-bae1-92437167ed28", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": "0e7d841f-6f2a-44e3-b2e9-b9e2a8fa6241", "select_options": {}}	2024-12-04 14:58:24.643109	0e7d841f-6f2a-44e3-b2e9-b9e2a8fa6241	\N	7	7	\N	{}	{}	1.0
10	device_description	Device Description	ELN Device Description	icon-device_description	t		f	6	{}	\N	2025-10-24 11:06:21.601233	2025-10-24 11:06:21.603058	\N	\N	{}	\N	ef683325-7db2-4b7f-afac-13385db0c7b4	\N	\N	\N	\N	{}	{}	\N
\.


--
-- Data for Name: element_klasses_revisions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.element_klasses_revisions (id, element_klass_id, uuid, properties_release, released_at, released_by, created_by, created_at, updated_at, deleted_at, version) FROM stdin;
1	1	5f59fd06-c442-4f78-abb1-765061989227	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "5f59fd06-c442-4f78-abb1-765061989227", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.703305	\N	\N	2024-01-23 13:44:01.71634	2024-01-23 13:44:01.71634	\N	\N
2	2	e066565a-a4a6-4933-b725-c42c92dab64d	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "e066565a-a4a6-4933-b725-c42c92dab64d", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.718844	\N	\N	2024-01-23 13:44:01.723034	2024-01-23 13:44:01.723034	\N	\N
3	3	900859ad-916e-4093-98c1-e8a87270ae64	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "900859ad-916e-4093-98c1-e8a87270ae64", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.724862	\N	\N	2024-01-23 13:44:01.728263	2024-01-23 13:44:01.728263	\N	\N
4	4	85e19d00-7d22-4310-911c-ba17f234992e	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "85e19d00-7d22-4310-911c-ba17f234992e", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.73005	\N	\N	2024-01-23 13:44:01.733502	2024-01-23 13:44:01.733502	\N	\N
5	5	6e8c7739-908b-4026-a38c-eee668384baf	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "6e8c7739-908b-4026-a38c-eee668384baf", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.735182	\N	\N	2024-01-23 13:44:01.738642	2024-01-23 13:44:01.738642	\N	\N
6	6	194a26e0-2663-4f76-a529-2fb6e5bc0ddf	{"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "uuid": "194a26e0-2663-4f76-a529-2fb6e5bc0ddf", "klass": "ElementKlass", "select_options": {}}	2024-01-23 13:44:01.740399	\N	\N	2024-01-23 13:44:01.743908	2024-01-23 13:44:01.743908	\N	\N
11	8	27604871-84ad-4c55-80a0-5698118c9ef1	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "labimotion": "1.1.4"}, "uuid": "27604871-84ad-4c55-80a0-5698118c9ef1", "klass": "ElementKlass", "layers": {}, "select_options": {}}	2024-03-20 11:27:36.266044	7	\N	2024-03-20 11:27:36.281682	2024-03-20 11:27:36.281682	\N	\N
7	7	287821ac-a60b-4b1c-bec4-31f8e6318523	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "labimotion": "1.1.1"}, "uuid": "287821ac-a60b-4b1c-bec4-31f8e6318523", "klass": "ElementKlass", "layers": {}, "select_options": {}}	2024-01-24 07:02:39.235874	2	\N	2024-01-24 07:02:39.271325	2024-12-04 12:57:28.687055	2024-12-04 12:57:28.687043	\N
8	7	30e78480-dfa1-4e62-8260-8e7896ec7cad	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "30e78480-dfa1-4e62-8260-8e7896ec7cad", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	2024-01-24 07:03:05.11925	2	\N	2024-01-24 07:03:05.126699	2024-12-04 12:57:28.68769	2024-12-04 12:57:28.687684	1.0
12	8	6f6f17a4-dc54-41fd-a05d-f8ce851874f6	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "6f6f17a4-dc54-41fd-a05d-f8ce851874f6", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 286.5, "y": 400.84086914062493, "zoom": 2}}, "identifier": null, "select_options": {}}	2024-03-20 11:30:11.226838	7	\N	2024-03-20 11:30:11.242658	2024-03-20 11:30:11.242658	\N	1.0
13	8	078843ad-4de4-40b0-bca8-136a06459f50	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "078843ad-4de4-40b0-bca8-136a06459f50", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}, "fixed": {"wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-1-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "1", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 153.94964022108297, "y": 271.54511305952786, "zoom": 1.316636906723931}}, "identifier": null, "select_options": {}}	2024-03-21 10:38:44.892811	7	\N	2024-03-21 10:38:44.936366	2024-03-21 10:38:44.936366	\N	2.0
9	7	e53fa6b1-4ff8-4798-b7cb-799cd7048340	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "e53fa6b1-4ff8-4798-b7cb-799cd7048340", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.1", "identifier": null, "select_options": {}}	2024-02-16 08:48:13.380617	2	\N	2024-02-16 08:48:13.389489	2024-12-04 12:57:28.688091	2024-12-04 12:57:28.688086	1.1
10	7	8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "identifier": null, "select_options": {}}	2024-02-16 08:48:17.518249	2	\N	2024-02-16 08:48:17.527177	2024-12-04 12:57:28.688488	2024-12-04 12:57:28.688484	2.0
14	9	5ebf115b-f57b-4f33-b1b1-c68f9a896089	{"pkg": {"eln": {"version": "v1.10.2", "base_revision": "7e269bb594d29413788f3e5bfa16544981b5d392", "current_revision": "7e269bb594d29413788f3e5bfa16544981b5d392"}, "labimotion": "1.4.0.2"}, "uuid": "5ebf115b-f57b-4f33-b1b1-c68f9a896089", "klass": "ElementKlass", "layers": {}, "select_options": {}}	2024-12-04 12:57:51.931147	7	\N	2024-12-04 12:57:51.934562	2024-12-04 12:57:51.934562	\N	\N
15	9	5c136a3d-49f4-429e-a8e9-a0e7090d9956	{"pkg": {"eln": {"version": "v1.10.2", "base_revision": "7e269bb594d29413788f3e5bfa16544981b5d392", "current_revision": "7e269bb594d29413788f3e5bfa16544981b5d392"}, "name": "chem-generic-ui", "version": "1.4.4", "labimotion": "1.4.0.2"}, "uuid": "5c136a3d-49f4-429e-a8e9-a0e7090d9956", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "748041a1-1639-424d-9147-1f5ea2436c43", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "017cd221-2419-44f1-a1b6-16411b7aa44f", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "a2c7b308-b1d5-447b-b3dd-8b090c11f4c1", "type": "label", "value": "TEST"}, {"id": "b21ffab0-8e17-4934-bb45-218ef371348d", "type": "number", "value": ""}, {"id": "087203bc-2493-4b2d-bae1-92437167ed28", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": "0e7d841f-6f2a-44e3-b2e9-b9e2a8fa6241", "select_options": {}}	2024-12-04 14:58:24.643109	7	\N	2024-12-04 14:58:24.654953	2024-12-04 14:58:24.654953	\N	1.0
\.


--
-- Data for Name: element_tags; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.element_tags (id, taggable_type, taggable_id, taggable_data, created_at, updated_at) FROM stdin;
2	Sample	1	{"collection_labels": [{"id": 4, "name": "TEST 1", "user_id": 2, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-01-23 15:17:46.432546	2024-01-23 15:17:46.432546
5	Labimotion::Element	3	{"collection_labels": [{"id": 11, "name": "API_TEST_a3a7c777-6924-4ab2-a1b3-18c959051931", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-03-21 10:32:02.045545	2024-03-21 10:32:02.045545
6	Labimotion::Element	4	{"collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-03-21 10:41:42.526193	2024-03-21 10:41:42.526193
7	Labimotion::Element	5	{"collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-03-21 12:13:25.247046	2024-03-21 12:13:25.247046
1	Molecule	1	{"pubchem_cid": 222, "pubchem_lcss": {"Record": {"Section": [{"Section": [{"URL": "https://www.osha.gov/sites/default/files/publications/OSHA3514.pdf", "Section": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/", "TOCHeading": "GHS Classification", "Description": "GHS (Globally Harmonized System of Classification and Labelling of Chemicals) is a United Nations system to identify hazardous chemicals and to inform users about these hazards. GHS has been adopted by many countries around the world and is now also used as the basis for international and national transport regulations for dangerous goods. The GHS hazard statements, class categories, pictograms, signal words, and the precautionary statements can be found on the PubChem GHS page.", "Information": [{"Name": "Note", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Italics", "Start": 0, "Length": 185}], "String": "Pictograms displayed are for > 99.9% (3511 of 3512) of reports that indicate hazard statements. This chemical does not meet GHS hazard criteria for < 0.1% (1  of 3512) of reports."}]}, "ReferenceNumber": 47}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS04.svg", "Type": "Icon", "Extra": "Compressed Gas", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS05.svg", "Type": "Icon", "Extra": "Corrosive", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS06.svg", "Type": "Icon", "Extra": "Acute Toxic", "Start": 2, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 3, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 4, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 47}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 47}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 29, "Length": 6}], "String": "H221 (87.7%): Flammable gas [Danger Flammable gases]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 66, "Length": 7}], "String": "H280 (29.6%): Contains gas under pressure; may explode if heated [Warning Gases under pressure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 57, "Length": 6}], "String": "H314 (> 99.9%): Causes severe skin burns and eye damage [Danger Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 32, "Length": 6}], "String": "H331 (87.6%): Toxic if inhaled [Danger Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 34, "Length": 7}], "String": "H332 (11.6%): Harmful if inhaled [Warning Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 48, "Length": 7}], "String": "H335 (11.8%): May cause respiratory irritation [Warning Specific target organ toxicity, single exposure; Respiratory tract irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 44, "Length": 7}], "String": "H400 (> 99.9%): Very toxic to aquatic life [Warning Hazardous to the aquatic environment, acute hazard]"}, {"String": "H411 (29.2%): Toxic to aquatic life with long lasting effects [Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 47}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P210, P260, P261, P264, P271, P273, P280, P301+P330+P331, P302+P361+P354, P304+P340, P305+P354+P338, P316, P317, P319, P321, P363, P377, P381, P391, P403, P403+P233, P405, P410+P403, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 47}, {"Name": "ECHA C&L Notifications Summary", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Italics", "Start": 0, "Length": 179}], "String": "Aggregated GHS information provided per 3512 reports by companies from 57 notifications to the ECHA C&L Inventory. Each notification may be associated with multiple companies."}, {"Markup": [{"Type": "Italics", "Start": 0, "Length": 146}, {"URL": "https://echa.europa.eu/information-on-chemicals/cl-inventory-database/-/discli/details/11196", "Start": 125, "Length": 20}], "String": "Reported as not meeting GHS hazard criteria per 1 of 3512 reports by companies. For more detailed information, please visit  ECHA C&L website."}, {"Markup": [{"Type": "Italics", "Start": 0, "Length": 103}], "String": "There are 56 notifications provided by 3511 of 3512 reports by companies with hazard statement code(s)."}, {"Markup": [{"Type": "Italics", "Start": 0, "Length": 281}], "String": "Information may vary between notifications depending on impurities, additives, and other factors. The percentage value in parenthesis indicates the notified classification ratio from companies that provide hazard codes. Only hazard codes with percentage values above 10% are shown."}]}, "ReferenceNumber": 47}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS05.svg", "Type": "Icon", "Extra": "Corrosive", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS06.svg", "Type": "Icon", "Extra": "Acute Toxic", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 2, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 3, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 59}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 59}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 21, "Length": 6}], "String": "H221: Flammable gas [Danger Flammable gases]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 28, "Length": 7}], "String": "H302: Harmful if swallowed [Warning Acute toxicity, oral]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 47, "Length": 6}], "String": "H314: Causes severe skin burns and eye damage [Danger Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 24, "Length": 6}], "String": "H331: Toxic if inhaled [Danger Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 34, "Length": 7}], "String": "H400: Very toxic to aquatic life [Warning Hazardous to the aquatic environment, acute hazard]"}]}, "ReferenceNumber": 59}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P210, P260, P261, P264, P270, P271, P273, P280, P301+P317, P301+P330+P331, P302+P361+P354, P304+P340, P305+P354+P338, P316, P321, P330, P363, P377, P381, P391, P403, P403+P233, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 59}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS04.svg", "Type": "Icon", "Extra": "Compressed Gas", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS05.svg", "Type": "Icon", "Extra": "Corrosive", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS06.svg", "Type": "Icon", "Extra": "Acute Toxic", "Start": 2, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 3, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 60}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 60}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 21, "Length": 6}], "String": "H221: Flammable gas [Danger Flammable gases]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 58, "Length": 7}], "String": "H280: Contains gas under pressure; may explode if heated [Warning Gases under pressure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 47, "Length": 6}], "String": "H314: Causes severe skin burns and eye damage [Danger Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 33, "Length": 6}], "String": "H318: Causes serious eye damage [Danger Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 24, "Length": 6}], "String": "H331: Toxic if inhaled [Danger Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 34, "Length": 7}], "String": "H400: Very toxic to aquatic life [Warning Hazardous to the aquatic environment, acute hazard]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 60, "Length": 7}], "String": "H410: Very toxic to aquatic life with long lasting effects [Warning Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 60}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P210, P260, P261, P264, P264+P265, P271, P273, P280, P301+P330+P331, P302+P361+P354, P304+P340, P305+P354+P338, P316, P317, P321, P363, P377, P381, P391, P403, P403+P233, P405, P410+P403, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 60}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS02.svg", "Type": "Icon", "Extra": "Flammable", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS04.svg", "Type": "Icon", "Extra": "Compressed Gas", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS05.svg", "Type": "Icon", "Extra": "Corrosive", "Start": 2, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 3, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 4, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 5, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 82}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 82}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 31, "Length": 6}], "String": "H220: Extremely flammable gas [Danger Flammable gases]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 58, "Length": 7}], "String": "H280: Contains gas under pressure; may explode if heated [Warning Gases under pressure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 47, "Length": 6}], "String": "H314: Causes severe skin burns and eye damage [Danger Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 33, "Length": 6}], "String": "H318: Causes serious eye damage [Danger Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 26, "Length": 7}], "String": "H332: Harmful if inhaled [Warning Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 81, "Length": 6}], "String": "H334: May cause allergy or asthma symptoms or breathing difficulties if inhaled [Danger Sensitization, respiratory]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 31, "Length": 6}], "String": "H370: Causes damage to organs [Danger Specific target organ toxicity, single exposure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 74, "Length": 7}], "String": "H373: May causes damage to organs through prolonged or repeated exposure [Warning Specific target organ toxicity, repeated exposure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 34, "Length": 7}], "String": "H400: Very toxic to aquatic life [Warning Hazardous to the aquatic environment, acute hazard]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 60, "Length": 7}], "String": "H410: Very toxic to aquatic life with long lasting effects [Warning Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 82}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P203, P210, P222, P233, P260, P261, P264, P264+P265, P270, P271, P273, P280, P284, P301+P330+P331, P302+P361+P354, P304+P340, P305+P354+P338, P308+P316, P316, P317, P319, P321, P342+P316, P363, P377, P381, P391, P403, P405, P410+P403, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 82}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS02.svg", "Type": "Icon", "Extra": "Flammable", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS04.svg", "Type": "Icon", "Extra": "Compressed Gas", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS05.svg", "Type": "Icon", "Extra": "Corrosive", "Start": 2, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 3, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 4, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 5, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 83}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 83}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 31, "Length": 6}], "String": "H220: Extremely flammable gas [Danger Flammable gases]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 58, "Length": 7}], "String": "H280: Contains gas under pressure; may explode if heated [Warning Gases under pressure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 47, "Length": 6}], "String": "H314: Causes severe skin burns and eye damage [Danger Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 33, "Length": 6}], "String": "H318: Causes serious eye damage [Danger Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 26, "Length": 7}], "String": "H332: Harmful if inhaled [Warning Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 81, "Length": 6}], "String": "H334: May cause allergy or asthma symptoms or breathing difficulties if inhaled [Danger Sensitization, respiratory]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 44, "Length": 7}], "String": "H341: Suspected of causing genetic defects [Warning Germ cell mutagenicity]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 31, "Length": 6}], "String": "H370: Causes damage to organs [Danger Specific target organ toxicity, single exposure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 74, "Length": 7}], "String": "H373: May causes damage to organs through prolonged or repeated exposure [Warning Specific target organ toxicity, repeated exposure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 34, "Length": 7}], "String": "H400: Very toxic to aquatic life [Warning Hazardous to the aquatic environment, acute hazard]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 60, "Length": 7}], "String": "H410: Very toxic to aquatic life with long lasting effects [Warning Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 83}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P203, P210, P222, P233, P260, P261, P264, P264+P265, P270, P271, P273, P280, P284, P301+P330+P331, P302+P361+P354, P304+P340, P305+P354+P338, P308+P316, P316, P317, P318, P319, P321, P342+P316, P363, P377, P381, P391, P403, P405, P410+P403, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 83}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"String": "H402: Harmful to aquatic life [Hazardous to the aquatic environment, acute hazard]"}]}, "ReferenceNumber": 84}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P273, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 84}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"String": "Not Classified"}]}, "ReferenceNumber": 85}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS02.svg", "Type": "Icon", "Extra": "Flammable", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS04.svg", "Type": "Icon", "Extra": "Compressed Gas", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS05.svg", "Type": "Icon", "Extra": "Corrosive", "Start": 2, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 3, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 4, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 86}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 86}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 31, "Length": 6}], "String": "H220: Extremely flammable gas [Danger Flammable gases]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 58, "Length": 7}], "String": "H280: Contains gas under pressure; may explode if heated [Warning Gases under pressure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 47, "Length": 6}], "String": "H314: Causes severe skin burns and eye damage [Danger Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 33, "Length": 6}], "String": "H318: Causes serious eye damage [Danger Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 26, "Length": 7}], "String": "H332: Harmful if inhaled [Warning Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 81, "Length": 6}], "String": "H334: May cause allergy or asthma symptoms or breathing difficulties if inhaled [Danger Sensitization, respiratory]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 31, "Length": 6}], "String": "H370: Causes damage to organs [Danger Specific target organ toxicity, single exposure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 70, "Length": 6}], "String": "H372: Causes damage to organs through prolonged or repeated exposure [Danger Specific target organ toxicity, repeated exposure]"}]}, "ReferenceNumber": 86}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P203, P210, P222, P233, P260, P261, P264, P264+P265, P270, P271, P280, P284, P301+P330+P331, P302+P361+P354, P304+P340, P305+P354+P338, P308+P316, P316, P317, P319, P321, P342+P316, P363, P377, P381, P403, P405, P410+P403, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 86}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS04.svg", "Type": "Icon", "Extra": "Compressed Gas", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS05.svg", "Type": "Icon", "Extra": "Corrosive", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS06.svg", "Type": "Icon", "Extra": "Acute Toxic", "Start": 2, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 3, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 99}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 99}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 21, "Length": 6}], "String": "H221: Flammable gas [Danger Flammable gases]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 47, "Length": 6}], "String": "H314: Causes severe skin burns and eye damage [Danger Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 24, "Length": 6}], "String": "H331: Toxic if inhaled [Danger Acute toxicity, inhalation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 34, "Length": 7}], "String": "H400: Very toxic to aquatic life [Warning Hazardous to the aquatic environment, acute hazard]"}]}, "ReferenceNumber": 99}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P210, P260, P261, P264, P271, P273, P280, P301+P330+P331, P302+P361+P354, P304+P340, P305+P354+P338, P316, P321, P363, P377, P381, P391, P403, P403+P233, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 99}], "DisplayControls": {"ShowAtMost": 1, "CreateTable": {"ColumnContents": ["Name", "Value"], "NumberOfColumns": 2, "FromInformationIn": "ThisSection"}}}], "TOCHeading": "Hazards Identification", "Description": "This section identifies the hazards of the chemical presented on the safety data sheet (SDS) and the appropriate warning information associated with those hazards.  The information in this section includes, but are not limited to, the hazard classification of the chemical, signal word, pictograms, hazard statements and precautionary statements.", "Information": [{"Name": "ERG Hazard Classes", "Value": {"StringWithMarkup": [{"String": "Toxic/poison by inhalation (TIH/PIH)"}]}, "ReferenceNumber": 33}]}], "TOCHeading": "Safety and Hazards", "Description": "Information on safety and hazards for this compound, including safety/hazards properties, reactivity, incompatibilities, management techniques, first aid treatments, and more.  For toxicity and related information, please see the Toxicity section."}], "Reference": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/erg/", "ANID": 39280829, "Name": "Ammonia", "SourceID": "45d2a3a006c4667a6d3f9f0b8d5e06c9", "LicenseURL": "https://www.transportation.gov/web-policies", "SourceName": "Emergency Response Guidebook (ERG)", "Description": "The Emergency Response Guidebook 2024 provides first responders with a manual intended for use during the initial phase of a transportation incident involving hazardous materials/dangerous goods. PubChem integration of ERG information provides more opportunities for users/first responders to find ERG data and additional safety, toxicity, and more chemical information. For more information, please visit ERG website (https://www.phmsa.dot.gov/training/hazmat/erg/emergency-response-guidebook-erg) and/or the ERG summary table (https://pubchem.ncbi.nlm.nih.gov/erg/).", "ReferenceNumber": 33}, {"URL": "https://echa.europa.eu/information-on-chemicals/cl-inventory-database/-/discli/details/11196", "ANID": 1854204, "Name": "Ammonia, anhydrous (EC: 231-635-3)", "SourceID": "11196", "LicenseURL": "https://echa.europa.eu/web/guest/legal-notice", "SourceName": "European Chemicals Agency (ECHA)", "Description": "The information provided here is aggregated from the \\"Notified classification and labelling\\" from ECHA's C&L Inventory. Read more: https://echa.europa.eu/information-on-chemicals/cl-inventory-database", "LicenseNote": "Use of the information, documents and data from the ECHA website is subject to the terms and conditions of this Legal Notice, and subject to other binding limitations provided for under applicable law, the information, documents and data made available on the ECHA website may be reproduced, distributed and/or used, totally or in part, for non-commercial purposes provided that ECHA is acknowledged as the source: \\"Source: European Chemicals Agency, http://echa.europa.eu/\\". Such acknowledgement must be included in each copy of the material. ECHA permits and encourages organisations and individuals to create links to the ECHA website under the following cumulative conditions: Links can only be made to webpages that provide a link to the Legal Notice page.", "ReferenceNumber": 47}, {"URL": "http://hcis.safeworkaustralia.gov.au/HazardousChemical/Details?chemicalID=225", "ANID": 2279015, "Name": "Ammonia gas", "SourceID": "225", "SourceName": "Hazardous Chemical Information System (HCIS), Safe Work Australia", "Description": "The Hazardous Chemical Information System (HCIS) at the Safe Work Australia is a database of chemical classifications and workplace exposure standards. It allows users to find information on chemicals that have been classified in accordance with the GHS or which have an Australian Workplace Exposure Standard.", "ReferenceNumber": 59}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/source/hsdb/162", "ANID": 122, "Name": "Ammonia", "IsToxnet": true, "SourceID": "162", "LicenseURL": "https://www.nlm.nih.gov/web_policies.html", "SourceName": "Hazardous Substances Data Bank (HSDB)", "Description": "The Hazardous Substances Data Bank (HSDB) is a toxicology database that focuses on the toxicology of potentially hazardous chemicals. It provides information on human exposure, industrial hygiene, emergency handling procedures, environmental fate, regulatory requirements, nanomaterials, and related areas. The information in HSDB has been assessed by a Scientific Review Panel.", "ReferenceNumber": 60}, {"URL": "https://www.nite.go.jp/chem/english/ghs/09-mhlw-2003e.html", "ANID": 8787865, "Name": "Ammonia - FY2009 (Revised classification)", "SourceID": "21B3003", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 82}, {"URL": "https://www.nite.go.jp/chem/english/ghs/06-imcg-0557e.html", "ANID": 8787866, "Name": "Ammonia - FY2006 (New/original classication)", "SourceID": "564", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 83}, {"URL": "https://www.nite.go.jp/chem/english/ghs/21-moe-2031e.html", "ANID": 39312838, "Name": "Ammonia - FY2021 (Revised classification)", "SourceID": "R03_C_031B_MOE", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 84}, {"URL": "https://www.nite.go.jp/chem/english/ghs/16-moe-0007e.html", "ANID": 39312839, "Name": "Ammonia - FY2016 (Revised classification)", "SourceID": "H28_K_007B", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 85}, {"URL": "https://www.nite.go.jp/chem/english/ghs/14-mhlw-2011e.html", "ANID": 39312840, "Name": "Ammonia - FY2014 (Revised classification)", "SourceID": "H26_B_011__", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 86}, {"URL": "https://eur-lex.europa.eu/eli/reg/2008/1272/2023-07-31", "ANID": 391813, "Name": "ammonia, anhydrous", "SourceID": "007-001-00-5", "LicenseURL": "https://eur-lex.europa.eu/content/legal-notice/legal-notice.html", "SourceName": "Regulation (EC) No 1272/2008 of the European Parliament and of the Council", "Description": "Regulation (EC) No 1272/2008 of the European Parliament and of the Council of 16 December 2008 on classification, labelling and packaging of substances and mixtures.", "LicenseNote": "The copyright for the editorial content of this source, the summaries of EU legislation and the consolidated texts, which is owned by the EU, is licensed under the Creative Commons Attribution 4.0 International licence.", "ReferenceNumber": 99}], "RecordType": "CID", "RecordTitle": "Ammonia", "RecordNumber": 222}}}	2024-01-23 15:17:17.524154	2024-09-27 09:09:45.213979
9	Molecule	2	{"pubchem_cid": 6331, "pubchem_lcss": null}	2024-11-20 06:12:29.252337	2024-11-20 06:12:33.609213
11	Molecule	3	{"pubchem_cid": 7002, "pubchem_lcss": {"Record": {"Section": [{"Section": [{"URL": "https://www.osha.gov/sites/default/files/publications/OSHA3514.pdf", "Section": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/", "TOCHeading": "GHS Classification", "Description": "GHS (Globally Harmonized System of Classification and Labelling of Chemicals) is a United Nations system to identify hazardous chemicals and to inform users about these hazards. GHS has been adopted by many countries around the world and is now also used as the basis for international and national transport regulations for dangerous goods. The GHS hazard statements, class categories, pictograms, signal words, and the precautionary statements can be found on the PubChem GHS page.", "Information": [{"Name": "Note", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Italics", "Start": 0, "Length": 176}], "String": "Pictograms displayed are for 95.7% (1814 of 1895) of reports that indicate hazard statements. This chemical does not meet GHS hazard criteria for 4.3% (81  of 1895) of reports."}]}, "ReferenceNumber": 28}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 2, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 28}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 28}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 36, "Length": 7}], "String": "H302 (94.7%): Harmful if swallowed [Warning Acute toxicity, oral]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 58, "Length": 6}], "String": "H304 (90%): May be fatal if swallowed and enters airways [Danger Aspiration hazard]"}, {"String": "H411 (13%): Toxic to aquatic life with long lasting effects [Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 28}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P264, P270, P273, P301+P316, P301+P317, P330, P331, P391, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 28}, {"Name": "ECHA C&L Notifications Summary", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Italics", "Start": 0, "Length": 179}], "String": "Aggregated GHS information provided per 1895 reports by companies from 13 notifications to the ECHA C&L Inventory. Each notification may be associated with multiple companies."}, {"Markup": [{"Type": "Italics", "Start": 0, "Length": 147}, {"URL": "https://echa.europa.eu/information-on-chemicals/cl-inventory-database/-/discli/details/20442", "Start": 126, "Length": 20}], "String": "Reported as not meeting GHS hazard criteria per 81 of 1895 reports by companies. For more detailed information, please visit  ECHA C&L website."}, {"Markup": [{"Type": "Italics", "Start": 0, "Length": 103}], "String": "There are 12 notifications provided by 1814 of 1895 reports by companies with hazard statement code(s)."}, {"Markup": [{"Type": "Italics", "Start": 0, "Length": 281}], "String": "Information may vary between notifications depending on impurities, additives, and other factors. The percentage value in parenthesis indicates the notified classification ratio from companies that provide hazard codes. Only hazard codes with percentage values above 10% are shown."}]}, "ReferenceNumber": 28}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 0, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 29}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 0, "Length": 7}], "String": "Warning"}]}, "ReferenceNumber": 29}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 35, "Length": 7}], "String": "H302 (100%): Harmful if swallowed [Warning Acute toxicity, oral]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 44, "Length": 7}], "String": "H319 (100%): Causes serious eye irritation [Warning Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 47, "Length": 7}], "String": "H335 (100%): May cause respiratory irritation [Warning Specific target organ toxicity, single exposure; Respiratory tract irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 48, "Length": 7}], "String": "H336 (100%): May cause drowsiness or dizziness [Warning Specific target organ toxicity, single exposure; Narcotic effects]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 81, "Length": 7}], "String": "H373 (100%): May causes damage to organs through prolonged or repeated exposure [Warning Specific target organ toxicity, repeated exposure]"}, {"String": "H411 (100%): Toxic to aquatic life with long lasting effects [Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 29}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P260, P261, P264, P264+P265, P270, P271, P273, P280, P301+P317, P304+P340, P305+P351+P338, P319, P330, P337+P317, P391, P403+P233, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 29}, {"Name": "ECHA C&L Notifications Summary", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Italics", "Start": 0, "Length": 92}], "String": "The GHS information provided by 1 company from 1 notification to the ECHA C&L Inventory."}]}, "ReferenceNumber": 29}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 2, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 39}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 0, "Length": 6}], "String": "Danger"}]}, "ReferenceNumber": 39}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 26, "Length": 7}], "String": "H227: Combustible liquid [Warning Flammable liquids]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 28, "Length": 7}], "String": "H302: Harmful if swallowed [Warning Acute toxicity, oral]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 30, "Length": 7}], "String": "H315: Causes skin irritation [Warning Skin corrosion/irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 37, "Length": 7}], "String": "H319: Causes serious eye irritation [Warning Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSDanger", "Start": 81, "Length": 6}], "String": "H334: May cause allergy or asthma symptoms or breathing difficulties if inhaled [Danger Sensitization, respiratory]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 40, "Length": 7}], "String": "H335: May cause respiratory irritation [Warning Specific target organ toxicity, single exposure; Respiratory tract irritation]"}, {"String": "H401: Toxic to aquatic life [Hazardous to the aquatic environment, acute hazard]"}, {"String": "H411: Toxic to aquatic life with long lasting effects [Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 39}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P210, P233, P260, P261, P264, P264+P265, P270, P271, P273, P280, P284, P301+P317, P302+P352, P304+P340, P305+P351+P338, P319, P321, P330, P332+P317, P337+P317, P342+P316, P362+P364, P370+P378, P391, P403, P403+P233, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 39}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 2, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 75}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 0, "Length": 7}], "String": "Warning"}]}, "ReferenceNumber": 75}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 26, "Length": 7}], "String": "H227: Combustible liquid [Warning Flammable liquids]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 28, "Length": 7}], "String": "H302: Harmful if swallowed [Warning Acute toxicity, oral]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 37, "Length": 7}], "String": "H319: Causes serious eye irritation [Warning Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 40, "Length": 7}], "String": "H335: May cause respiratory irritation [Warning Specific target organ toxicity, single exposure; Respiratory tract irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 41, "Length": 7}], "String": "H336: May cause drowsiness or dizziness [Warning Specific target organ toxicity, single exposure; Narcotic effects]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 74, "Length": 7}], "String": "H373: May causes damage to organs through prolonged or repeated exposure [Warning Specific target organ toxicity, repeated exposure]"}, {"String": "H401: Toxic to aquatic life [Hazardous to the aquatic environment, acute hazard]"}, {"String": "H411: Toxic to aquatic life with long lasting effects [Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 75}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P210, P260, P261, P264, P264+P265, P270, P271, P273, P280, P301+P317, P304+P340, P305+P351+P338, P319, P330, P337+P317, P370+P378, P391, P403, P403+P233, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 75}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 2, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 76}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 0, "Length": 7}], "String": "Warning"}]}, "ReferenceNumber": 76}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 26, "Length": 7}], "String": "H227: Combustible liquid [Warning Flammable liquids]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 28, "Length": 7}], "String": "H302: Harmful if swallowed [Warning Acute toxicity, oral]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 37, "Length": 7}], "String": "H319: Causes serious eye irritation [Warning Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 40, "Length": 7}], "String": "H335: May cause respiratory irritation [Warning Specific target organ toxicity, single exposure; Respiratory tract irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 41, "Length": 7}], "String": "H336: May cause drowsiness or dizziness [Warning Specific target organ toxicity, single exposure; Narcotic effects]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 74, "Length": 7}], "String": "H373: May causes damage to organs through prolonged or repeated exposure [Warning Specific target organ toxicity, repeated exposure]"}, {"String": "H401: Toxic to aquatic life [Hazardous to the aquatic environment, acute hazard]"}, {"String": "H411: Toxic to aquatic life with long lasting effects [Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 76}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P210, P260, P261, P264, P264+P265, P270, P271, P273, P280, P301+P317, P304+P340, P305+P351+P338, P319, P330, P337+P317, P370+P378, P391, P403, P403+P233, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 76}, {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS07.svg", "Type": "Icon", "Extra": "Irritant", "Start": 0, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS08.svg", "Type": "Icon", "Extra": "Health Hazard", "Start": 1, "Length": 1}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/images/ghs/GHS09.svg", "Type": "Icon", "Extra": "Environmental Hazard", "Start": 2, "Length": 1}], "String": "          "}]}, "ReferenceNumber": 77}, {"Name": "Signal", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 0, "Length": 7}], "String": "Warning"}]}, "ReferenceNumber": 77}, {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": [{"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 37, "Length": 7}], "String": "H319: Causes serious eye irritation [Warning Serious eye damage/eye irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 40, "Length": 7}], "String": "H335: May cause respiratory irritation [Warning Specific target organ toxicity, single exposure; Respiratory tract irritation]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 41, "Length": 7}], "String": "H336: May cause drowsiness or dizziness [Warning Specific target organ toxicity, single exposure; Narcotic effects]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 74, "Length": 7}], "String": "H373: May causes damage to organs through prolonged or repeated exposure [Warning Specific target organ toxicity, repeated exposure]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 34, "Length": 7}], "String": "H400: Very toxic to aquatic life [Warning Hazardous to the aquatic environment, acute hazard]"}, {"Markup": [{"Type": "Color", "Extra": "GHSWarning", "Start": 60, "Length": 7}], "String": "H410: Very toxic to aquatic life with long lasting effects [Warning Hazardous to the aquatic environment, long-term hazard]"}]}, "ReferenceNumber": 77}, {"Name": "Precautionary Statement Codes", "Value": {"StringWithMarkup": [{"String": "P260, P261, P264+P265, P271, P273, P280, P304+P340, P305+P351+P338, P319, P337+P317, P391, P403+P233, P405, and P501"}, {"Markup": [{"URL": "https://pubchem.ncbi.nlm.nih.gov/ghs/#_prec", "Start": 64, "Length": 18}], "String": "(The corresponding statement to each P-code can be found at the GHS Classification page.)"}]}, "ReferenceNumber": 77}], "DisplayControls": {"ShowAtMost": 1, "CreateTable": {"ColumnContents": ["Name", "Value"], "NumberOfColumns": 2, "FromInformationIn": "ThisSection"}}}], "TOCHeading": "Hazards Identification", "Description": "This section identifies the hazards of the chemical presented on the safety data sheet (SDS) and the appropriate warning information associated with those hazards.  The information in this section includes, but are not limited to, the hazard classification of the chemical, signal word, pictograms, hazard statements and precautionary statements."}], "TOCHeading": "Safety and Hazards", "Description": "Information on safety and hazards for this compound, including safety/hazards properties, reactivity, incompatibilities, management techniques, first aid treatments, and more.  For toxicity and related information, please see the Toxicity section."}], "Reference": [{"URL": "https://echa.europa.eu/information-on-chemicals/cl-inventory-database/-/discli/details/20442", "ANID": 1857041, "Name": "1-methylnaphthalene (EC: 201-966-8)", "SourceID": "20442", "LicenseURL": "https://echa.europa.eu/web/guest/legal-notice", "SourceName": "European Chemicals Agency (ECHA)", "Description": "The information provided here is aggregated from the \\"Notified classification and labelling\\" from ECHA's C&L Inventory. Read more: https://echa.europa.eu/information-on-chemicals/cl-inventory-database", "LicenseNote": "Use of the information, documents and data from the ECHA website is subject to the terms and conditions of this Legal Notice, and subject to other binding limitations provided for under applicable law, the information, documents and data made available on the ECHA website may be reproduced, distributed and/or used, totally or in part, for non-commercial purposes provided that ECHA is acknowledged as the source: \\"Source: European Chemicals Agency, http://echa.europa.eu/\\". Such acknowledgement must be included in each copy of the material. ECHA permits and encourages organisations and individuals to create links to the ECHA website under the following cumulative conditions: Links can only be made to webpages that provide a link to the Legal Notice page.", "ReferenceNumber": 28}, {"URL": "https://echa.europa.eu/information-on-chemicals/cl-inventory-database/-/discli/details/128874", "ANID": 1888956, "Name": "Methylnaphthalene (EC: 215-329-7)", "SourceID": "128874", "LicenseURL": "https://echa.europa.eu/web/guest/legal-notice", "SourceName": "European Chemicals Agency (ECHA)", "Description": "The information provided here is aggregated from the \\"Notified classification and labelling\\" from ECHA's C&L Inventory. Read more: https://echa.europa.eu/information-on-chemicals/cl-inventory-database", "LicenseNote": "Use of the information, documents and data from the ECHA website is subject to the terms and conditions of this Legal Notice, and subject to other binding limitations provided for under applicable law, the information, documents and data made available on the ECHA website may be reproduced, distributed and/or used, totally or in part, for non-commercial purposes provided that ECHA is acknowledged as the source: \\"Source: European Chemicals Agency, http://echa.europa.eu/\\". Such acknowledgement must be included in each copy of the material. ECHA permits and encourages organisations and individuals to create links to the ECHA website under the following cumulative conditions: Links can only be made to webpages that provide a link to the Legal Notice page.", "ReferenceNumber": 29}, {"URL": "https://pubchem.ncbi.nlm.nih.gov/source/hsdb/5268", "ANID": 3339, "Name": "1-METHYLNAPHTHALENE", "IsToxnet": true, "SourceID": "5268", "LicenseURL": "https://www.nlm.nih.gov/web_policies.html", "SourceName": "Hazardous Substances Data Bank (HSDB)", "Description": "The Hazardous Substances Data Bank (HSDB) is a toxicology database that focuses on the toxicology of potentially hazardous chemicals. It provides information on human exposure, industrial hygiene, emergency handling procedures, environmental fate, regulatory requirements, nanomaterials, and related areas. The information in HSDB has been assessed by a Scientific Review Panel.", "ReferenceNumber": 39}, {"URL": "https://www.nite.go.jp/chem/english/ghs/15-mhlw-0045e.html", "ANID": 39311682, "Name": "1-Methylnaphthalene - FY2015 (Revised classification)", "SourceID": "H27_B_024_C_045B_P", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 75}, {"URL": "https://www.nite.go.jp/chem/english/ghs/08-meti-0066e.html", "ANID": 39311683, "Name": "1-methylnaphthalene - FY2008 (New/original classication)", "SourceID": "1_438_1)", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 76}, {"URL": "https://www.nite.go.jp/chem/english/ghs/22-jniosh-0016e.html", "ANID": 39312581, "Name": "Methylnaphthalene - FY2022 (New/original classication)", "SourceID": "R04_A_016_JNIOSH,MOE", "SourceName": "NITE-CMC", "Description": "The chemical classification in this section was conducted by the Chemical Management Center (CMC) of Japan National Institute of Technology and Evaluation (NITE) in accordance with GHS Classification Guidance for the Japanese Government, and is intended to provide a reference for preparing GHS labelling and SDS for users.", "ReferenceNumber": 77}], "RecordType": "CID", "RecordTitle": "1-Methylnaphthalene", "RecordNumber": 7002}}}	2024-11-20 06:14:08.080107	2024-11-20 06:14:09.173464
8	Sample	2	{"reaction_id": 1, "collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-11-20 06:11:55.316893	2024-11-20 06:14:26.456684
10	Sample	3	{"reaction_id": 1, "collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-11-20 06:12:56.651298	2024-11-20 06:14:26.482592
12	Sample	4	{"reaction_id": 1, "collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-11-20 06:14:15.812668	2024-11-20 06:14:26.509198
13	Reaction	1	{"user_labels": [], "collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2024-11-20 06:14:26.384435	2024-11-20 06:15:17.621966
15	Sample	5	{"reaction_id": 2, "collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2025-11-13 04:54:36.621388	2025-11-13 04:54:36.732637
16	Sample	6	{"reaction_id": 2, "collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2025-11-13 04:54:36.797966	2025-11-13 04:54:36.8375
14	Reaction	2	{"user_labels": [], "collection_labels": [{"id": 11, "name": "FIXED", "user_id": 7, "is_shared": false, "shared_by_id": null, "is_synchronized": false}]}	2025-11-13 04:54:36.238245	2025-11-13 04:55:55.119739
\.


--
-- Data for Name: elemental_compositions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.elemental_compositions (id, sample_id, composition_type, data, loading, created_at, updated_at, log_data) FROM stdin;
1	1	found		\N	2024-01-23 15:17:46.443292	2024-01-23 15:17:46.443292	{"h": [{"c": {"id": 1, "data": "{}", "loading": null, "sample_id": 1, "created_at": "2024-01-23T15:17:46.443292", "updated_at": "2024-01-23T15:17:46.443292", "composition_type": "found"}, "v": 1, "ts": 1706023066443}], "v": 1}
2	1	formula	"H"=>"17.76", "N"=>"82.24"	\N	2024-01-23 15:17:46.445584	2024-01-23 15:17:46.445584	{"h": [{"c": {"id": 2, "data": "{\\"H\\": \\"17.76\\", \\"N\\": \\"82.24\\"}", "loading": null, "sample_id": 1, "created_at": "2024-01-23T15:17:46.445584", "updated_at": "2024-01-23T15:17:46.445584", "composition_type": "formula"}, "v": 1, "ts": 1706023066446}], "v": 1}
3	2	found		\N	2024-11-20 06:11:55.321262	2024-11-20 06:11:55.321262	{"h": [{"c": {"id": 3, "data": "{}", "loading": null, "sample_id": 2, "created_at": "2024-11-20T06:11:55.321262", "updated_at": "2024-11-20T06:11:55.321262", "composition_type": "found"}, "v": 1, "ts": 1732083115321}], "v": 1}
4	2	formula	"H"=>"17.76", "N"=>"82.24"	\N	2024-11-20 06:11:55.32201	2024-11-20 06:11:55.32201	{"h": [{"c": {"id": 4, "data": "{\\"H\\": \\"17.76\\", \\"N\\": \\"82.24\\"}", "loading": null, "sample_id": 2, "created_at": "2024-11-20T06:11:55.32201", "updated_at": "2024-11-20T06:11:55.32201", "composition_type": "formula"}, "v": 1, "ts": 1732083115322}], "v": 1}
5	3	found		\N	2024-11-20 06:12:56.655652	2024-11-20 06:12:56.655652	{"h": [{"c": {"id": 5, "data": "{}", "loading": null, "sample_id": 3, "created_at": "2024-11-20T06:12:56.655652", "updated_at": "2024-11-20T06:12:56.655652", "composition_type": "found"}, "v": 1, "ts": 1732083176656}], "v": 1}
6	3	formula	"B"=>"78.14", "H"=>"21.86"	\N	2024-11-20 06:12:56.656432	2024-11-20 06:12:56.656432	{"h": [{"c": {"id": 6, "data": "{\\"B\\": \\"78.14\\", \\"H\\": \\"21.86\\"}", "loading": null, "sample_id": 3, "created_at": "2024-11-20T06:12:56.656432", "updated_at": "2024-11-20T06:12:56.656432", "composition_type": "formula"}, "v": 1, "ts": 1732083176656}], "v": 1}
7	4	found		\N	2024-11-20 06:14:15.816253	2024-11-20 06:14:15.816253	{"h": [{"c": {"id": 7, "data": "{}", "loading": null, "sample_id": 4, "created_at": "2024-11-20T06:14:15.816253", "updated_at": "2024-11-20T06:14:15.816253", "composition_type": "found"}, "v": 1, "ts": 1732083255816}], "v": 1}
8	4	formula	"C"=>"92.91", "H"=>"7.09"	\N	2024-11-20 06:14:15.816797	2024-11-20 06:14:15.816797	{"h": [{"c": {"id": 8, "data": "{\\"C\\": \\"92.91\\", \\"H\\": \\"7.09\\"}", "loading": null, "sample_id": 4, "created_at": "2024-11-20T06:14:15.816797", "updated_at": "2024-11-20T06:14:15.816797", "composition_type": "formula"}, "v": 1, "ts": 1732083255817}], "v": 1}
9	5	found		\N	2025-11-13 04:54:36.631013	2025-11-13 04:54:36.631013	{"h": [{"c": {"id": 9, "data": "{}", "loading": null, "sample_id": 5, "created_at": "2025-11-13T04:54:36.631013", "updated_at": "2025-11-13T04:54:36.631013", "composition_type": "found"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676631}], "v": 1}
10	5	formula	"C"=>"92.91", "H"=>"7.09"	\N	2025-11-13 04:54:36.633316	2025-11-13 04:54:36.633316	{"h": [{"c": {"id": 10, "data": "{\\"C\\": \\"92.91\\", \\"H\\": \\"7.09\\"}", "loading": null, "sample_id": 5, "created_at": "2025-11-13T04:54:36.633316", "updated_at": "2025-11-13T04:54:36.633316", "composition_type": "formula"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676633}], "v": 1}
11	6	found		\N	2025-11-13 04:54:36.805129	2025-11-13 04:54:36.805129	{"h": [{"c": {"id": 11, "data": "{}", "loading": null, "sample_id": 6, "created_at": "2025-11-13T04:54:36.805129", "updated_at": "2025-11-13T04:54:36.805129", "composition_type": "found"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676805}], "v": 1}
12	6	formula	"H"=>"17.76", "N"=>"82.24"	\N	2025-11-13 04:54:36.807001	2025-11-13 04:54:36.807001	{"h": [{"c": {"id": 12, "data": "{\\"H\\": \\"17.76\\", \\"N\\": \\"82.24\\"}", "loading": null, "sample_id": 6, "created_at": "2025-11-13T04:54:36.807001", "updated_at": "2025-11-13T04:54:36.807001", "composition_type": "formula"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676807}], "v": 1}
\.


--
-- Data for Name: elements; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.elements (id, name, element_klass_id, short_label, properties, created_by, created_at, updated_at, deleted_at, uuid, klass_uuid, properties_release, ancestry) FROM stdin;
3	New Workflow	8	API-WRK1	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "bbedce98-ca37-48da-999c-1b020b3772f5", "klass": "Element", "layers": {"one": {"ai": [], "wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "Nr 3(three)"}], "text_sub_fields": []}], "wf_info": {"node_id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f"}, "wf_uuid": "72d43a4c-dfca-4675-be87-ac294835412d", "position": 10, "timeRecord": "", "wf_position": 1}}, "version": "1.0", "identifier": null, "klass_uuid": "6f6f17a4-dc54-41fd-a05d-f8ce851874f6"}	7	2024-03-21 10:32:02.030721	2024-03-21 10:32:02.030721	\N	bbedce98-ca37-48da-999c-1b020b3772f5	6f6f17a4-dc54-41fd-a05d-f8ce851874f6	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "6f6f17a4-dc54-41fd-a05d-f8ce851874f6", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 286.5, "y": 400.84086914062493, "zoom": 2}}, "identifier": null, "select_options": {}}	\N
4	New Workflow	8	API-WRK2	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "85006e6b-5990-4324-bbac-5d069cd31150", "klass": "Element", "layers": {"one": {"ai": [], "wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "value": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "Nr 3(three)"}], "text_sub_fields": []}], "wf_info": {"node_id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f"}, "wf_uuid": "d7c31a6d-f2d5-453b-9b90-2b0ea03b24e0", "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"ai": [], "wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "wf_info": {"node_id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "source_layer": "three"}, "position": 40, "timeRecord": "", "wf_position": 2}, "four": {"ai": [], "wf": false, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "wf_uuid": null, "position": 20, "timeRecord": "", "wf_position": 1}, "fixed": {"ai": [], "wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"ai": [], "wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "value": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "Nr 4(four)"}], "text_sub_fields": []}], "wf_info": {"node_id": "a9d76db6-4136-4a3a-8750-8ede5169f6db"}, "wf_uuid": "f1fb38f9-5e28-48a1-b5de-3fce70ef7a18", "position": 40, "timeRecord": "", "wf_position": 1}, "three.1": {"ai": [], "wf": true, "key": "three.1", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "Nr 4(four)"}], "text_sub_fields": []}], "wf_info": {"node_id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "source_layer": "one"}, "position": 20, "timeRecord": "", "wf_position": 2}}, "version": "2.0", "identifier": null, "klass_uuid": "078843ad-4de4-40b0-bca8-136a06459f50"}	7	2024-03-21 10:41:42.513557	2024-03-21 10:41:42.513557	\N	85006e6b-5990-4324-bbac-5d069cd31150	078843ad-4de4-40b0-bca8-136a06459f50	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "078843ad-4de4-40b0-bca8-136a06459f50", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}, "fixed": {"wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-1-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "1", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 153.94964022108297, "y": 271.54511305952786, "zoom": 1.316636906723931}}, "identifier": null, "select_options": {}}	\N
5	New Workflow	8	API-WRK3	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "4b23e4ca-9994-4b85-aadb-062bf15e9af2", "klass": "Element", "layers": {"one": {"ai": [], "wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "Nr 3(three)"}], "text_sub_fields": []}], "wf_info": {"node_id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f"}, "wf_uuid": "389460bf-1f80-40c6-ab6b-32e1ed58435d", "position": 20, "timeRecord": "", "wf_position": 1}, "fixed": {"ai": [], "wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"ai": [], "wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "Nr 4(four)"}], "text_sub_fields": []}], "wf_info": {"node_id": "a9d76db6-4136-4a3a-8750-8ede5169f6db"}, "wf_uuid": "3767b63b-5a94-4564-9eb3-275c1a94231c", "position": 40, "timeRecord": "", "wf_position": 1}}, "version": "2.0", "identifier": null, "klass_uuid": "078843ad-4de4-40b0-bca8-136a06459f50"}	7	2024-03-21 12:13:25.234452	2024-03-21 12:13:25.234452	\N	4b23e4ca-9994-4b85-aadb-062bf15e9af2	078843ad-4de4-40b0-bca8-136a06459f50	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "078843ad-4de4-40b0-bca8-136a06459f50", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}, "fixed": {"wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-1-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "1", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 153.94964022108297, "y": 271.54511305952786, "zoom": 1.316636906723931}}, "identifier": null, "select_options": {}}	\N
2	New Tryout	7	MSU-T2	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "08eaf995-65ad-4f33-90e1-2f552a740ffa", "klass": "Element", "layers": {"one": {"ai": [], "wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "value": "HALLO", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "identifier": null, "klass_uuid": "8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6"}	2	2024-02-16 08:49:01.282633	2024-12-04 12:57:28.677412	2024-12-04 12:57:28.677407	08eaf995-65ad-4f33-90e1-2f552a740ffa	8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "identifier": null, "select_options": {}}	\N
1	New Tryout	7	MSU-T1	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "face37f2-4760-4197-9d10-114d78264448", "klass": "Element", "layers": {"one": {"ai": [], "wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "klass_uuid": "30e78480-dfa1-4e62-8260-8e7896ec7cad"}	2	2024-01-24 08:17:12.523778	2024-12-04 12:57:28.668778	2024-12-04 12:57:28.668764	face37f2-4760-4197-9d10-114d78264448	30e78480-dfa1-4e62-8260-8e7896ec7cad	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "30e78480-dfa1-4e62-8260-8e7896ec7cad", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	\N
\.


--
-- Data for Name: elements_elements; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.elements_elements (id, element_id, parent_id, created_by, created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: elements_revisions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.elements_revisions (id, element_id, uuid, klass_uuid, name, properties, created_by, created_at, updated_at, deleted_at, properties_release) FROM stdin;
3	3	bbedce98-ca37-48da-999c-1b020b3772f5	6f6f17a4-dc54-41fd-a05d-f8ce851874f6	New Workflow	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "bbedce98-ca37-48da-999c-1b020b3772f5", "klass": "Element", "layers": {"one": {"ai": [], "wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "Nr 3(three)"}], "text_sub_fields": []}], "wf_info": {"node_id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f"}, "wf_uuid": "72d43a4c-dfca-4675-be87-ac294835412d", "position": 10, "timeRecord": "", "wf_position": 1}}, "version": "1.0", "identifier": null, "klass_uuid": "6f6f17a4-dc54-41fd-a05d-f8ce851874f6"}	\N	2024-03-21 10:32:02.156786	2024-03-21 10:32:02.156786	\N	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "6f6f17a4-dc54-41fd-a05d-f8ce851874f6", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 286.5, "y": 400.84086914062493, "zoom": 2}}, "identifier": null, "select_options": {}}
4	4	85006e6b-5990-4324-bbac-5d069cd31150	078843ad-4de4-40b0-bca8-136a06459f50	New Workflow	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "85006e6b-5990-4324-bbac-5d069cd31150", "klass": "Element", "layers": {"one": {"ai": [], "wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "value": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "Nr 3(three)"}], "text_sub_fields": []}], "wf_info": {"node_id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f"}, "wf_uuid": "d7c31a6d-f2d5-453b-9b90-2b0ea03b24e0", "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"ai": [], "wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "wf_info": {"node_id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "source_layer": "three"}, "position": 40, "timeRecord": "", "wf_position": 2}, "four": {"ai": [], "wf": false, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "wf_uuid": null, "position": 20, "timeRecord": "", "wf_position": 1}, "fixed": {"ai": [], "wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"ai": [], "wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "value": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "Nr 4(four)"}], "text_sub_fields": []}], "wf_info": {"node_id": "a9d76db6-4136-4a3a-8750-8ede5169f6db"}, "wf_uuid": "f1fb38f9-5e28-48a1-b5de-3fce70ef7a18", "position": 40, "timeRecord": "", "wf_position": 1}, "three.1": {"ai": [], "wf": true, "key": "three.1", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "Nr 4(four)"}], "text_sub_fields": []}], "wf_info": {"node_id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "source_layer": "one"}, "position": 20, "timeRecord": "", "wf_position": 2}}, "version": "2.0", "identifier": null, "klass_uuid": "078843ad-4de4-40b0-bca8-136a06459f50"}	\N	2024-03-21 10:41:42.638735	2024-03-21 10:41:42.638735	\N	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "078843ad-4de4-40b0-bca8-136a06459f50", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}, "fixed": {"wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-1-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "1", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 153.94964022108297, "y": 271.54511305952786, "zoom": 1.316636906723931}}, "identifier": null, "select_options": {}}
5	5	4b23e4ca-9994-4b85-aadb-062bf15e9af2	078843ad-4de4-40b0-bca8-136a06459f50	New Workflow	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "4b23e4ca-9994-4b85-aadb-062bf15e9af2", "klass": "Element", "layers": {"one": {"ai": [], "wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "Nr 3(three)"}], "text_sub_fields": []}], "wf_info": {"node_id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f"}, "wf_uuid": "389460bf-1f80-40c6-ab6b-32e1ed58435d", "position": 20, "timeRecord": "", "wf_position": 1}, "fixed": {"ai": [], "wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"ai": [], "wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "wf-next", "field": "_wf_next", "label": "Next", "default": "", "position": 2, "required": false, "sub_fields": [], "wf_options": [{"key": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "Nr 2(two)"}, {"key": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "Nr 4(four)"}], "text_sub_fields": []}], "wf_info": {"node_id": "a9d76db6-4136-4a3a-8750-8ede5169f6db"}, "wf_uuid": "3767b63b-5a94-4564-9eb3-275c1a94231c", "position": 40, "timeRecord": "", "wf_position": 1}}, "version": "2.0", "identifier": null, "klass_uuid": "078843ad-4de4-40b0-bca8-136a06459f50"}	\N	2024-03-21 12:13:25.354497	2024-03-21 12:13:25.354497	\N	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.1.1", "labimotion": "1.1.4"}, "uuid": "078843ad-4de4-40b0-bca8-136a06459f50", "klass": "ElementKlass", "layers": {"one": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}, "two": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}, "four": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}, "fixed": {"wf": false, "key": "fixed", "cols": 1, "color": "none", "label": "Fixed", "style": "panel_generic_heading", "fields": [], "position": 10, "timeRecord": "", "wf_position": 0}, "three": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "flowObject": {"edges": [{"id": "reactflow__edge-1-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "label": "next", "source": "1", "target": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-9cf7ae08-035d-4d7c-9a3b-e20728e63409", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-a9d76db6-4136-4a3a-8750-8ede5169f6db-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "label": "next", "source": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "target": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-cb1bbed3-667a-4f3f-8d5c-5374d951f7b0-2", "label": "next", "source": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-9cf7ae08-035d-4d7c-9a3b-e20728e63409-2", "label": "next", "source": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f-2", "label": "next", "source": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "target": "2", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}, {"id": "reactflow__edge-1-a9d76db6-4136-4a3a-8750-8ede5169f6db", "label": "next", "source": "1", "target": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "animated": true, "markerEnd": {"type": "arrowclosed"}, "sourceHandle": null, "targetHandle": null}], "nodes": [{"id": "1", "data": {"label": "Start"}, "type": "input", "width": 150, "height": 39, "dragging": false, "position": {"x": 257.5, "y": -182.42043457031247}, "selected": false, "deletable": false, "positionAbsolute": {"x": 257.5, "y": -182.42043457031247}}, {"id": "2", "data": {"label": "End"}, "type": "output", "width": 150, "height": 39, "position": {"x": 250, "y": 255}, "deletable": false, "positionAbsolute": {"x": 250, "y": 255}}, {"id": "c5b4ccca-65a0-4132-9d7e-0c91e2cc9d2f", "data": {"lKey": "one", "layer": {"wf": true, "key": "one", "cols": 1, "color": "none", "label": "Nr 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_one", "label": "name_one", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 20, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 318.61363983154297, "y": -83.2996917724609}, "positionAbsolute": {"x": 318.61363983154297, "y": -83.2996917724609}}, {"id": "9cf7ae08-035d-4d7c-9a3b-e20728e63409", "data": {"lKey": "two", "layer": {"wf": true, "key": "two", "cols": 1, "color": "none", "label": "Nr 2", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_two", "label": "name_two", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 30, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "dragging": false, "position": {"x": 107.11363983154297, "y": 85.2003082275391}, "selected": false, "positionAbsolute": {"x": 107.11363983154297, "y": 85.2003082275391}}, {"id": "a9d76db6-4136-4a3a-8750-8ede5169f6db", "data": {"lKey": "three", "layer": {"wf": true, "key": "three", "cols": 1, "color": "none", "label": "Nr 3", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_three", "label": "name_three", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 40, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 533.613639831543, "y": 47.2003082275391}, "positionAbsolute": {"x": 533.613639831543, "y": 47.2003082275391}}, {"id": "cb1bbed3-667a-4f3f-8d5c-5374d951f7b0", "data": {"lKey": "four", "layer": {"wf": true, "key": "four", "cols": 1, "color": "none", "label": "Nr 4", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "name_four", "label": "name_four", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 50, "timeRecord": "", "wf_position": 0}}, "type": "default", "width": 150, "height": 57, "position": {"x": 418.61363983154297, "y": 158.7003082275391}, "positionAbsolute": {"x": 418.61363983154297, "y": 158.7003082275391}}], "viewport": {"x": 153.94964022108297, "y": 271.54511305952786, "zoom": 1.316636906723931}}, "identifier": null, "select_options": {}}
2	2	08eaf995-65ad-4f33-90e1-2f552a740ffa	8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6	New Tryout	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "08eaf995-65ad-4f33-90e1-2f552a740ffa", "klass": "Element", "layers": {"one": {"ai": [], "wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "value": "HALLO", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "identifier": null, "klass_uuid": "8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6"}	\N	2024-02-16 08:49:01.416848	2024-12-04 12:57:28.6766	2024-12-04 12:57:28.676594	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "8853b3d9-2ba9-46fc-bc07-eb0b4bbaf4a6", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}, {"type": "table", "field": "Table", "label": "Table", "default": "", "position": 2, "required": false, "sub_fields": [{"id": "30848b11-f353-4b4d-8879-249f3de60f00", "type": "text", "value": "", "col_name": "Col 1"}, {"id": "f46818d3-bd57-49e9-a4de-7edfa319b972", "type": "text", "value": "", "col_name": "Col 2"}], "text_sub_fields": []}, {"type": "input-group", "field": "Group", "label": "Group", "default": "", "position": 3, "required": false, "sub_fields": [{"id": "f35ab349-63c7-4849-9e3b-db41a7d8c9dc", "type": "label", "value": "TEST"}, {"id": "edc174e1-05cc-400f-a2f9-00516c5c33ab", "type": "number", "value": ""}, {"id": "8b9223a1-ea34-4f69-93fc-3dc5e4865e7f", "type": "text", "value": ""}], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "2.0", "identifier": null, "select_options": {}}
1	1	face37f2-4760-4197-9d10-114d78264448	30e78480-dfa1-4e62-8260-8e7896ec7cad	New Tryout	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "face37f2-4760-4197-9d10-114d78264448", "klass": "Element", "layers": {"one": {"ai": [], "wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "klass_uuid": "30e78480-dfa1-4e62-8260-8e7896ec7cad"}	\N	2024-01-24 08:17:12.645707	2024-12-04 12:57:28.665581	2024-12-04 12:57:28.665569	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "30e78480-dfa1-4e62-8260-8e7896ec7cad", "klass": "ElementKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "Nr. 1", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}
\.


--
-- Data for Name: elements_samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.elements_samples (id, element_id, sample_id, created_by, created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: experiments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.experiments (id, type, name, description, status, parameter, user_id, device_id, container_id, experimentable_id, experimentable_type, ancestry, parent_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: fingerprints; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.fingerprints (id, fp0, fp1, fp2, fp3, fp4, fp5, fp6, fp7, fp8, fp9, fp10, fp11, fp12, fp13, fp14, fp15, num_set_bits, created_at, updated_at, deleted_at) FROM stdin;
1	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0	2024-01-23 15:17:46.387447	2024-01-23 15:17:46.387447	\N
2	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000100000	1	2024-11-20 06:12:56.643615	2024-11-20 06:12:56.643615	\N
3	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000010000000000000000000000010000001000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000100001000000	0000000000000000000000000000000001000000000000001000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000010000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000001000000000000000000000001000	0000000000000000000000000000000000000000010000000000000000000000	0000000000000000000000000000000010000000000000000000000000000000	0000000000000000000000000000000000000000000000000000000000000000	0000000000000000000000000000000000000000000000100000000000000000	0000000000000000000000000000000000000000000000000000000000000000	13	2024-11-20 06:14:15.798414	2024-11-20 06:14:15.798414	\N
\.


--
-- Data for Name: inventories; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.inventories (id, prefix, name, counter, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ketcherails_amino_acids; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ketcherails_amino_acids (id, moderated_by, suggested_by, name, molfile, aid, aid2, bid, icon_path, sprite_class, status, notes, approved_at, rejected_at, created_at, updated_at, icon_file_name, icon_content_type, icon_file_size, icon_updated_at) FROM stdin;
\.


--
-- Data for Name: ketcherails_atom_abbreviations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ketcherails_atom_abbreviations (id, moderated_by, suggested_by, name, molfile, aid, bid, icon_path, sprite_class, status, notes, approved_at, rejected_at, created_at, updated_at, icon_file_name, icon_content_type, icon_file_size, icon_updated_at, rtl_name) FROM stdin;
\.


--
-- Data for Name: ketcherails_common_templates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ketcherails_common_templates (id, moderated_by, suggested_by, name, molfile, icon_path, sprite_class, notes, approved_at, rejected_at, created_at, updated_at, template_category_id, status, icon_file_name, icon_content_type, icon_file_size, icon_updated_at) FROM stdin;
1	\N	\N	Schwefelsalz-6-ring	\r\n  Ketcher 07261614192D 1   1.00000     0.00000     0\r\n\r\n 12 11  0     0  0            999 V2000\r\n    3.7544   -0.3333    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    4.6204   -0.8333    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    4.6204   -1.8333    0.0000 S   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.7544   -2.3333    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.8883   -1.8333    0.0000 S   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.8883   -0.8333    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.7544   -3.3333    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.1383   -1.8083    0.0000 B   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.1383   -0.8083    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.1384   -1.8083    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.1383   -2.8083    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.1383   -1.8083    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  3  4  2  0     0  0\r\n  4  5  1  0     0  0\r\n  4  7  1  0     0  0\r\n  5  6  1  0     0  0\r\n  6  1  1  0     0  0\r\n  8  9  1  0     0  0\r\n  8 10  1  0     0  0\r\n  8 11  1  0     0  0\r\n  8 12  1  0     0  0\r\nM  CHG  2   3   1   8  -1\r\nM  END\r\n	templates/9afa97572162db251ee07b2c9faa3e9deb372bed4de510894df3471acf7dd548.png	icons_small_3fe5b4121439a81f830c7e44f89c666eb74890a6e2e36eea68730d6e5149c02b20160826-27944-1o43zgj		2016-07-26 12:20:28	\N	2016-07-26 12:20:28	2016-11-30 09:46:29	\N	approved	3fe5b4121439a81f830c7e44f89c666eb74890a6e2e36eea68730d6e5149c02b20160826-27944-1o43zgj.png	image/png	3918	2016-08-26 14:11:42
7	\N	\N	cysteine	\r\n  ChemDraw08161617062D\r\n\r\n  7  6  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.4124    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.4124    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2374    0.0000 S   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\nM  END\r\n	templates/222454aeb09dfec9a8da8bbdcb05f49dbeeb0d0538b4c4ce816b37c27213d1dd.png	icons_small_45bca80abcb703553fbeb895c8ca298eaedfca44878c8ebd497e7568f052000d20160826-27944-1e6xfif		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:29	6	approved	45bca80abcb703553fbeb895c8ca298eaedfca44878c8ebd497e7568f052000d20160826-27944-1e6xfif.png	image/png	2803	2016-08-26 14:11:41
3	\N	\N	alanine	\r\n  ChemDraw08161617062D\r\n\r\n  6  5  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.8250    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.8250    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\nM  END\r\n	templates/8d909a6b3f9733746ed360c5fa8a78457d466eda94ea2e167167e6e93fc3cd17.png	icons_small_19af19fe685e313b32408d223df83bafc48d5bb3677375d576554de3f2b98b5220160826-27944-1vbjb4x		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:29	6	approved	19af19fe685e313b32408d223df83bafc48d5bb3677375d576554de3f2b98b5220160826-27944-1vbjb4x.png	image/png	2997	2016-08-26 14:11:40
4	\N	\N	arginine	\r\n  ChemDraw08161617062D\r\n\r\n 12 11  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    2.0624    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    2.0624    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.0624    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    2.0624    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.8874    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2374    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.0624    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.8874    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -2.0624    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n 10 12  2  0      \r\nM  END\r\n	templates/b2d6c02eb4d7dd1b8f4eb611b2d7b2110ebcb8d44b16117fb0335a7d0ba07903.png	icons_small_1bf197fb1fa3eb67800c0f37cf153040419c7492a891d6b5d57a4cc59ca374df20160826-27944-fhi35i		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:29	6	approved	1bf197fb1fa3eb67800c0f37cf153040419c7492a891d6b5d57a4cc59ca374df20160826-27944-fhi35i.png	image/png	3067	2016-08-26 14:11:40
5	\N	\N	asparagine	\r\n  ChemDraw08161617062D\r\n\r\n  9  8  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.8249    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.0001    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.8249    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.6499    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.6499    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -0.8249    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  7  9  2  0      \r\nM  END\r\n	templates/0134c38cda9ebbaf73e5f2a0d406f9493c01dafab8e6d2be52f7202f3fa95d3b.png	icons_small_1b076e86e33a71a1c823cd0bbdeaf2ff121a283c05c2bc8704896e5e37b8b7af20160826-27944-2k805f		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:29	6	approved	1b076e86e33a71a1c823cd0bbdeaf2ff121a283c05c2bc8704896e5e37b8b7af20160826-27944-2k805f.png	image/png	3271	2016-08-26 14:11:40
6	\N	\N	aspartic acid	\r\n  ChemDraw08161617062D\r\n\r\n  9  8  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.8249    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.0001    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.8249    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.6499    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.6499    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -0.8249    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  7  9  2  0      \r\nM  END\r\n	templates/5775b868e9f771b4ee27b747dd6e873100c445c51e6dc1400bbae9381bfef9dc.png	icons_small_4b42a354615654bb9c8af96adea7fff767e694e21f7d5c876a49d4ecd836ce3120160826-27944-iifv8q		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:29	6	approved	4b42a354615654bb9c8af96adea7fff767e694e21f7d5c876a49d4ecd836ce3120160826-27944-iifv8q.png	image/png	3146	2016-08-26 14:11:41
30	\N	\N	9,10-dihydro-9,10-[1,2]benzenoanthracene	\r\n  Ketcher 07261614192D\r\n\r\n 20 24  0  0  0  0  0  0  0  0999 V2000\r\n   -0.0768   -1.4017    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9213   -1.6654    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4893   -1.0167    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3858   -0.6301    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0768   -0.3260    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3858    0.2855    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0652   -1.0151    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6365   -1.7204    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2318   -2.1264    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9598   -2.1264    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.4046   -1.4793    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8902   -1.0151    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3532   -0.9148    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.0002   -1.1574    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.4046   -1.7204    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.6767   -1.9646    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4246    0.5007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2629    1.5101    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3357    2.1264    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5864    1.2270    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  1  5  1  0      \r\n  5  6  2  0      \r\n  4  6  1  0      \r\n  4  7  1  0      \r\n  1  8  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n 10 11  1  0      \r\n 11 12  2  0      \r\n  7 12  1  0      \r\n  3 13  1  0      \r\n 13 14  2  0      \r\n 14 15  1  0      \r\n 15 16  2  0      \r\n  2 16  1  0      \r\n  5 17  1  0      \r\n 17 18  2  0      \r\n 18 19  1  0      \r\n 19 20  2  0      \r\n  6 20  1  0      \r\nM  END\r\n	templates/a53046acb1a190261e38e6b67cedb733e4ff3ce57de92cf60f8a269f2c3e63a7.png	icons_small_693271ab93eaa135a4c4c3bf4a85cec0965b1b1b662908c2b7aaff1422b6bff620160826-27944-7u0tx6		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	693271ab93eaa135a4c4c3bf4a85cec0965b1b1b662908c2b7aaff1422b6bff620160826-27944-7u0tx6.png	image/png	6499	2016-08-26 14:11:40
95	\N	\N	_3	\r\n  Ketcher 07261614192D\r\n\r\n  8  7  0  0  0  0  0  0  0  0999 V2000\r\n   -0.0000    0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3778    0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3778    0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3778   -0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3778   -0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  2  5  1  0      \r\n  5  6  1  0      \r\n  5  7  1  0      \r\n  5  8  1  0      \r\nM  END\r\n	\N	icons_small_da1efe33aee84dee00b4e360f0a4da26f664bf31486c2b89b950e416533ca75720160830-29185-dzjbrs		2016-08-30 06:51:26	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	da1efe33aee84dee00b4e360f0a4da26f664bf31486c2b89b950e416533ca75720160830-29185-dzjbrs.png	image/png	3948	2016-08-30 06:51:26
9	\N	\N	glutamine	\r\n  ChemDraw08161617062D\r\n\r\n 10  9  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    1.2374    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.0624    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2375    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.0624    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -1.2375    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  8 10  2  0      \r\nM  END\r\n	templates/c986d1c3234f909bf24f1ab2e215e409c3d84dc0f297d052e3111eb7b6bc3496.png	icons_small_3b3495e9eb830f9daace11858900d2b280a0794ca65fb9d4b549144a03394b7920160826-27944-1e747hk		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:29	6	approved	3b3495e9eb830f9daace11858900d2b280a0794ca65fb9d4b549144a03394b7920160826-27944-1e747hk.png	image/png	3122	2016-08-26 14:11:41
11	\N	\N	histidine	\r\n  ChemDraw08161617062D\r\n\r\n 11 11  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2375    1.0483    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125    1.0483    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125    1.0483    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125    0.2233    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2375    1.0483    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125    1.8734    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125   -0.6017    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0789   -1.0891    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8228   -1.8734    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0007   -1.8734    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2524   -1.0891    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  2  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n  7 11  2  0      \r\nM  END\r\n	templates/a02abb6c86e941bb0cef80b8dd4ab40fad4826414afdfe9433358bf7ae6503fb.png	icons_small_7c937d2e9ed931143ef8e184eea5f0c5859ea38a14289971ca66f7b8e0c377fa20160826-27944-17d5nj5		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:30	6	approved	7c937d2e9ed931143ef8e184eea5f0c5859ea38a14289971ca66f7b8e0c377fa20160826-27944-17d5nj5.png	image/png	4363	2016-08-26 14:11:41
12	\N	\N	lysine	\r\n  ChemDraw08161617062D\r\n\r\n 10  9  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    1.6499    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    1.6499    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.6499    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    1.6499    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.4749    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.8250    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.6499    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.4749    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\nM  END\r\n	templates/887c4a09091546458bbe40b815a23f88f0ec162c93a1f173fe5d4cb469af9d42.png	icons_small_45763d06670bf8a32846e946238aa8446929bca6d6110abc100bec543f77c71520160826-27944-bssypb		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:30	6	approved	45763d06670bf8a32846e946238aa8446929bca6d6110abc100bec543f77c71520160826-27944-bssypb.png	image/png	2417	2016-08-26 14:11:42
13	\N	\N	methionine	\r\n  ChemDraw08161617062D\r\n\r\n  9  8  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    1.2374    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.0624    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2375    0.0000 S   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.0624    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\nM  END\r\n	templates/75440fc7f3efd2c9dab1dc851f732af593dc0dcb72f865c2fb569b7292956180.png	icons_small_5e2391dfbb4485a865d0600b1307c466df3c1ba15629cbf9e513beffe009f1db20160826-27944-1i78398		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:30	6	approved	5e2391dfbb4485a865d0600b1307c466df3c1ba15629cbf9e513beffe009f1db20160826-27944-1i78398.png	image/png	3041	2016-08-26 14:11:42
15	\N	\N	proline	\r\n  ChemDraw08161617062D\r\n\r\n  8  8  0  0  0  0  0  0  0  0999 V2000\r\n    0.6159   -1.2354    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6159   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1685   -0.1561    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6551   -0.8229    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1685   -1.4911    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1685    0.6674    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6551    0.6674    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1685    1.4911    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  1  5  1  0      \r\n  3  6  1  0      \r\n  6  7  1  0      \r\n  6  8  2  0      \r\nM  END\r\n	templates/a0c5c459bd6caea509c3547bbb6ac2e5e3795266005e1626c8afe01f01844a4e.png	icons_small_9255db7dc50cf5f64a331ed7aa89255b00590953ab1f8736efaedd819afe805c20160826-27944-1tmh4ej		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:30	6	approved	9255db7dc50cf5f64a331ed7aa89255b00590953ab1f8736efaedd819afe805c20160826-27944-1tmh4ej.png	image/png	3610	2016-08-26 14:11:42
16	\N	\N	valin	\r\n  ChemDraw08161617062D\r\n\r\n  8  7  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.4124    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.4124    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  4  8  1  0      \r\nM  END\r\n	templates/97cbd3097ddb0705fcf692430ddb2a214b2d17b37a33f4502bcac3f2fd950e03.png	icons_small_920d74c3715812a3829c4b740a8beaa14a28e53f561338f774ca3787f7e0461f20160826-27944-1ezzrww		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:30	6	approved	920d74c3715812a3829c4b740a8beaa14a28e53f561338f774ca3787f7e0461f20160826-27944-1ezzrww.png	image/png	3648	2016-08-26 14:11:43
23	\N	\N	naphthalene	\r\n  Ketcher 07261614192D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n   -0.0015    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0015   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7130   -0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4288   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4288    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7130    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7159    0.8243    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4288    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4288   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7159   -0.8228    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  1  6  2  0      \r\n  1  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n  2 10  1  0      \r\nM  END\r\n	templates/f6660380164c006fa294d131a2975cf81658a7ab49b96ead2c557adc92bc0490.png	icons_small_dbb868dd5d61fe2cfb97a360d29534d4d3b49b2386989f828d65e6f78144c0cf20160826-27944-i3z5kx		2016-08-16 15:24:46	\N	2016-08-16 15:24:46	2016-11-30 09:46:30	1	approved	dbb868dd5d61fe2cfb97a360d29534d4d3b49b2386989f828d65e6f78144c0cf20160826-27944-i3z5kx.png	image/png	3879	2016-08-26 14:11:42
31	\N	\N	cyclohepta-1,3,5-triene	\r\n  Ketcher 07261614192D\r\n\r\n  7  7  0  0  0  0  0  0  0  0999 V2000\r\n   -0.9044    0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9044   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2587   -0.9263    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5459   -0.7441    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9044   -0.0022    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5459    0.7412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2587    0.9263    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  7  2  0      \r\n  1  7  1  0      \r\nM  END\r\n	templates/a95c7934680690fb1b44d0da8826defabdffd802056322e16c22de88bfd2a4fb.png	icons_small_a3a97daffc07bf88fc45a18b339f71b1c1b10ca21182d76c613ffa7227bf93a220160826-27944-1bdfrih		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	a3a97daffc07bf88fc45a18b339f71b1c1b10ca21182d76c613ffa7227bf93a220160826-27944-1bdfrih.png	image/png	4380	2016-08-26 14:11:41
19	\N	\N	cyclopropene	\r\n  Ketcher 07261614192D\r\n\r\n  3  3  0  0  0  0  0  0  0  0999 V2000\r\n   -0.3576    0.4121    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3576   -0.4121    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3576    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  1  3  1  0      \r\nM  END\r\n	templates/fbcd37eb463deb95e66f1847b75016f70e9d860a608cd771efb2c20e4286990c.png	icons_small_ca90a7fa046b5145f07b38079e53184dd67653907ee15b2d7f99da3880f2648f20160826-27944-wdfiv3		2016-08-16 15:24:46	\N	2016-08-16 15:24:46	2016-11-30 09:46:30	1	approved	ca90a7fa046b5145f07b38079e53184dd67653907ee15b2d7f99da3880f2648f20160826-27944-wdfiv3.png	image/png	2658	2016-08-26 14:11:41
20	\N	\N	cyclobutene	\r\n  Ketcher 07261614192D\r\n\r\n  4  4  0  0  0  0  0  0  0  0999 V2000\r\n   -0.4125    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  1  4  1  0      \r\nM  END\r\n	templates/fc63105156705fa49ba612cc0b4c2c61eced0b51916b4f4a3c58f43c63764c64.png	icons_small_efd946311ce4f242b4bd0bb310864521de376560731a0e76e2c6fd39bd2f46ea20160826-27944-1lw570b		2016-08-16 15:24:46	\N	2016-08-16 15:24:46	2016-11-30 09:46:30	1	approved	efd946311ce4f242b4bd0bb310864521de376560731a0e76e2c6fd39bd2f46ea20160826-27944-1lw570b.png	image/png	847	2016-08-26 14:11:41
21	\N	\N	indene	\r\n  Ketcher 07261614192D\r\n\r\n  9 10  0  0  0  0  0  0  0  0999 V2000\r\n   -1.3490    0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3490   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6348   -0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0809   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0809    0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6348    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8651   -0.6669    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3490    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8651    0.6683    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  1  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  2  0      \r\n  5  9  1  0      \r\nM  END\r\n	templates/eb63ce31d8b175a0857f43b05ea2b7744e8c9464c104b0d482ef1a10d8e00c20.png	icons_small_77a33c361ea4a887b43a877d08a2a0509f2fb4add3524bec0fb5b61d5caead4420160826-27944-xik7fo		2016-08-16 15:24:46	\N	2016-08-16 15:24:46	2016-11-30 09:46:30	1	approved	77a33c361ea4a887b43a877d08a2a0509f2fb4add3524bec0fb5b61d5caead4420160826-27944-xik7fo.png	image/png	4353	2016-08-26 14:11:42
22	\N	\N	pentalene	\r\n  Ketcher 07261614192D\r\n\r\n  8  9  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0271    0.0764    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0271   -0.7485    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2430   -1.0031    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2415   -0.3353    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2430    0.3324    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0271   -0.0807    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0271    0.7456    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2415    1.0031    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  1  5  1  0      \r\n  4  6  1  0      \r\n  6  7  1  0      \r\n  7  8  2  0      \r\n  5  8  1  0      \r\nM  END\r\n	templates/879ec6064311de57ca821780c08be71b4ba1f117a4bc393f9c1779c73969a8d9.png	icons_small_07ad356b75d1b6c8a9eed508ffcc9991ce9708c3da153ebffbb6e82a231e57bc20160826-27944-xsvezm		2016-08-16 15:24:46	\N	2016-08-16 15:24:46	2016-11-30 09:46:30	1	approved	07ad356b75d1b6c8a9eed508ffcc9991ce9708c3da153ebffbb6e82a231e57bc20160826-27944-xsvezm.png	image/png	4616	2016-08-26 14:11:42
32	\N	\N	cyclooctatetraene	\r\n  Ketcher 07261614192D\r\n\r\n  8  8  0  0  0  0  0  0  0  0999 V2000\r\n   -0.9960    0.4112    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9960   -0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4134   -0.9953    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4119   -0.9953    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9960   -0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9960    0.4112    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4119    0.9953    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4134    0.9953    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  6  7  1  0      \r\n  7  8  2  0      \r\n  1  8  1  0      \r\nM  END\r\n	templates/243a903bcfc3bfb72ad7a4e76e71cd0e1a1a395aad636c6c796ea5815010379b.png	icons_small_a02b5a8c38b88fa661f3d42b53860bc831990da996a9c5e82b8bbeb54b4ba34a20160826-27944-qc4bkr		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	a02b5a8c38b88fa661f3d42b53860bc831990da996a9c5e82b8bbeb54b4ba34a20160826-27944-qc4bkr.png	image/png	2293	2016-08-26 14:11:41
27	\N	\N	phenanthrene	\r\n  Ketcher 07261614192D\r\n\r\n 14 16  0  0  0  0  0  0  0  0999 V2000\r\n   -1.6507    0.3549    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.0618   -0.3578    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.6493   -1.0706    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8243   -1.0706    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4132   -0.3578    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8257    0.3564    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4118   -0.3578    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8243    0.3564    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4118    1.0721    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4132    1.0721    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8243   -1.0721    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6493   -1.0721    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.0618   -0.3578    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6493    0.3564    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  1  6  1  0      \r\n  5  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n  6 10  1  0      \r\n  7 11  1  0      \r\n 11 12  2  0      \r\n 12 13  1  0      \r\n 13 14  2  0      \r\n  8 14  1  0      \r\nM  END\r\n	templates/70583835e4c2e403a2b535428e9ba301949ba7de3211e2114fd323a0700be0f0.png	icons_small_b7fca80f70f31ff1db42e094e3e70935fdc9541d035fcbf0bf65f042bb303fdd20160826-27944-6fr68b		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	b7fca80f70f31ff1db42e094e3e70935fdc9541d035fcbf0bf65f042bb303fdd20160826-27944-6fr68b.png	image/png	4437	2016-08-26 14:11:42
28	\N	\N	triphenylene	\r\n  Ketcher 07261614192D\r\n\r\n 18 21  0  0  0  0  0  0  0  0999 V2000\r\n   -0.3594    0.4119    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3594   -0.4119    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3550   -0.8245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0694   -0.4119    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0694    0.4119    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3550    0.8245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0723    0.8230    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7838    0.4119    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7838   -0.4119    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0723   -0.8216    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7838    0.8245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7838    1.6497    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0694    2.0623    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3550    1.6497    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3550   -1.6497    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0694   -2.0623    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7838   -1.6497    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7838   -0.8245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  1  6  1  0      \r\n  1  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n  2 10  1  0      \r\n  5 11  1  0      \r\n 11 12  2  0      \r\n 12 13  1  0      \r\n 13 14  2  0      \r\n  6 14  1  0      \r\n  3 15  1  0      \r\n 15 16  2  0      \r\n 16 17  1  0      \r\n 17 18  2  0      \r\n  4 18  1  0      \r\nM  END\r\n	templates/e339e52df617fc90b39317ee0f4587f61336e4da994a1a8bcabab893babab011.png	icons_small_058babebaf3712df221148b8e0c9b87d829321a5b1e4774a980b578fe44ffcc420160826-27944-owhh0q		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	058babebaf3712df221148b8e0c9b87d829321a5b1e4774a980b578fe44ffcc420160826-27944-owhh0q.png	image/png	4679	2016-08-26 14:11:42
29	\N	\N	pyrene	\r\n  Ketcher 07261614192D\r\n\r\n 16 19  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7146    1.6493    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7146    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0015    0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7132    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7132    1.6493    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0015    2.0618    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0015   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7132   -0.8243    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4278   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4278    0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4278    0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4278   -0.4103    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7146   -0.8228    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7161   -1.6493    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0015   -2.0618    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7132   -1.6493    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  1  6  1  0      \r\n  3  7  2  0      \r\n  7  8  1  0      \r\n  8  9  2  0      \r\n  9 10  1  0      \r\n  4 10  2  0      \r\n  2 11  1  0      \r\n 11 12  2  0      \r\n 12 13  1  0      \r\n  7 13  1  0      \r\n 13 14  2  0      \r\n 14 15  1  0      \r\n 15 16  2  0      \r\n  8 16  1  0      \r\nM  END\r\n	templates/533d56a1e12f25a3a4723dfdf70e73432ba0ea10991644b78d7ff6a8de84fc39.png	icons_small_f29ee710b5b187378c9ba3e8fe629e80f62eb9cc8fb13eae85b6cb1844bc764f20160826-27944-l6syvb		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	f29ee710b5b187378c9ba3e8fe629e80f62eb9cc8fb13eae85b6cb1844bc764f20160826-27944-l6syvb.png	image/png	4264	2016-08-26 14:11:42
138	\N	\N	_12	\r\n  Ketcher 07261614192D\r\n\r\n  4  3  0  0  0  0  0  0  0  0999 V2000\r\n   -0.6180   -0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2060   -0.0000    0.0000 N   0  3  0  0  0  0  0  0  0  0  0  0\r\n    0.6180   -0.7148    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n    0.6180    0.7148    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  2  0      \r\nM  CHG  2   2   1   3  -1\r\nM  END\r\n	\N	icons_small_902a16f18f7ea4cb2e0c1a8aee9a550d6875a0c875c3d0c8490b019d01f1263520160830-1161-84fkc8		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	902a16f18f7ea4cb2e0c1a8aee9a550d6875a0c875c3d0c8490b019d01f1263520160830-1161-84fkc8.png	image/png	4201	2016-08-30 08:35:18
34	\N	\N	porphyrin	\r\n  Ketcher 07261614192D\r\n\r\n 24 28  0  0  0  0  0  0  0  0999 V2000\r\n   -2.0430   -1.5110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4819   -2.0624    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7243   -1.6459    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8480   -0.8857    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.6690   -0.7465    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4588    2.0076    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.0393    1.4169    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.6818    0.7174    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8926    0.8706    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7239    1.6627    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.0558   -0.0472    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.0297    1.5110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4686    2.0624    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7107    1.6752    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8643    0.8567    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6265    0.7462    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0047    2.0496    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5044   -2.0364    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.0558   -1.4752    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6683   -0.6881    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8501   -0.8709    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7106   -1.6627    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0112   -2.0494    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.0428    0.0179    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  1  5  1  0      \r\n  5 11  2  0      \r\n  3 23  1  0      \r\n  6  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n  6 10  2  0      \r\n 10 17  1  0      \r\n  8 11  1  0      \r\n 12 13  2  0      \r\n 13 14  1  0      \r\n 14 15  1  0      \r\n 15 16  2  0      \r\n 12 16  1  0      \r\n 16 24  1  0      \r\n 14 17  2  0      \r\n 18 19  2  0      \r\n 19 20  1  0      \r\n 20 21  1  0      \r\n 21 22  1  0      \r\n 18 22  1  0      \r\n 22 23  2  0      \r\n 20 24  2  0      \r\nM  END\r\n	templates/b6cd63784658fa3e0bea9c6c7c584ed7e6e6fd51d3854409f1cc4102dcfbef87.png	icons_small_34e09e7625f32cf2a023d3c4828369e8b7031b454e31d6383b5f7f065606213c20160826-27944-1d7iw80		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	34e09e7625f32cf2a023d3c4828369e8b7031b454e31d6383b5f7f065606213c20160826-27944-1d7iw80.png	image/png	10081	2016-08-26 14:11:42
35	\N	\N	benzoporphyrin	\r\n  Ketcher 07261614192D\r\n\r\n 40 48  0  0  0  0  0  0  0  0999 V2000\r\n   -2.0912   -1.5599    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5120   -2.1292    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7298   -1.6992    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8576   -0.9144    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7052   -0.7706    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4882    2.0726    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.0874    1.4628    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7184    0.7406    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9036    0.8988    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7294    1.7165    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.1044   -0.0487    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1133    1.5599    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5340    2.1292    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7516    1.7294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9101    0.8844    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6970    0.7704    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0228    2.1160    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5709   -2.1023    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1402   -1.5230    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7402   -0.7104    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8955   -0.8991    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7515   -1.7165    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0295   -2.1157    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1267    0.0185    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.8959    1.7770    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.0993    2.5633    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.5200    3.1325    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7374    2.9155    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7166    2.8964    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.5443    3.1104    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -3.1435    2.5007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.9151    1.6769    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7880   -2.8849    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.5743   -3.0882    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.1435   -2.5090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.9265   -1.7263    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.8739   -1.7770    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -3.0772   -2.5633    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.4979   -3.1325    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7153   -2.9155    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  1  5  1  0      \r\n  5 11  2  0      \r\n  3 23  1  0      \r\n  6  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n  6 10  2  0      \r\n 10 17  1  0      \r\n  8 11  1  0      \r\n 12 13  2  0      \r\n 13 14  1  0      \r\n 14 15  1  0      \r\n 15 16  2  0      \r\n 12 16  1  0      \r\n 16 24  1  0      \r\n 14 17  2  0      \r\n 18 19  2  0      \r\n 19 20  1  0      \r\n 20 21  1  0      \r\n 21 22  1  0      \r\n 18 22  1  0      \r\n 22 23  2  0      \r\n 20 24  2  0      \r\n 12 25  1  0      \r\n 25 26  2  0      \r\n 26 27  1  0      \r\n 27 28  2  0      \r\n 28 13  1  0      \r\n  6 29  1  0      \r\n 29 30  2  0      \r\n 30 31  1  0      \r\n 31 32  2  0      \r\n 32  7  1  0      \r\n 18 33  1  0      \r\n 33 34  2  0      \r\n 34 35  1  0      \r\n 35 36  2  0      \r\n 36 19  1  0      \r\n  1 37  1  0      \r\n 37 38  2  0      \r\n 38 39  1  0      \r\n 39 40  2  0      \r\n 40  2  1  0      \r\nM  END\r\n	templates/21d910fbfcfa74e1d68d9bcc849f5670d6fd921ca5b2e524be321859dba9e0be.png	icons_small_f71f0b24cc04bf14984f89e26eeabb827af2852ccba8cdf166bfed4118f0d7ae20160826-27944-1sc4819		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	f71f0b24cc04bf14984f89e26eeabb827af2852ccba8cdf166bfed4118f0d7ae20160826-27944-1sc4819.png	image/png	11369	2016-08-26 14:11:41
37	\N	\N	_1	\r\n  Ketcher 07261614192D\r\n\r\n  4  5  0  0  0  0  0  0  0  0999 V2000\r\n    0.0080    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0080   -0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7148   -0.0117    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7148    0.0131    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  1  3  1  0      \r\n  1  4  1  0      \r\n  2  4  1  0      \r\nM  END\r\n	templates/51f29ec1a20e2340dad65dd4db977492897d38b3fe3a567f69524a429f9a449d.png	icons_small_97bf4ba87ecfda851fc1f9f62ca26c01e39a81bdcb8737338b85d6d8e6f04d4d20160826-27944-khv5bc	test note	2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:31	2	approved	97bf4ba87ecfda851fc1f9f62ca26c01e39a81bdcb8737338b85d6d8e6f04d4d20160826-27944-khv5bc.png	image/png	2612	2016-08-26 14:11:37
38	\N	\N	_2	\r\n  Ketcher 07261614192D\r\n\r\n  5  6  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7977   -0.6273    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2222   -0.0794    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7977   -0.6273    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0124   -0.4714    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0124    0.6273    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  4  1  1  0      \r\n  1  2  1  0      \r\n  2  5  1  0      \r\n  4  3  1  0      \r\n  2  3  1  0      \r\n  4  5  1  0      \r\nM  END\r\n	templates/9e9ab807bfc8ae1c16b371519ab608d1cc8126dffd367d299e6345ba95a16acb.png	icons_small_50783486314058c053913c6332de6575cdd3a679f12909221bd43dec20165d9a20160826-27944-13dvgc		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:31	2	approved	50783486314058c053913c6332de6575cdd3a679f12909221bd43dec20165d9a20160826-27944-13dvgc.png	image/png	3093	2016-08-26 14:11:39
39	\N	\N	_3	\r\n  Ketcher 07261614192D\r\n\r\n  5  6  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7697    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7697   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0553   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0553    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7697   -0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  1  4  1  0      \r\n  3  5  1  0      \r\n  4  5  1  0      \r\nM  END\r\n	templates/034782357dbb0183f9fef5911fc61df144fee03d9d2310fda71c33112b216a6b.png	icons_small_b17b954fd6261b70687b68537e09c0553398fdd415190fee2c15c51170c496cd20160826-27944-1vuxl3d		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:31	2	approved	b17b954fd6261b70687b68537e09c0553398fdd415190fee2c15c51170c496cd20160826-27944-1vuxl3d.png	image/png	2302	2016-08-26 14:11:39
40	\N	\N	_4	\r\n  Ketcher 07261614192D\r\n\r\n  6  7  0  0  0  0  0  0  0  0999 V2000\r\n   -0.2512   -0.5417    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9860   -0.8975    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5765   -0.1917    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1510    0.1772    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2512    0.8975    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9860   -0.6578    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  1  5  1  0      \r\n  4  5  1  0      \r\n  4  6  1  0      \r\n  1  6  1  0      \r\nM  END\r\n	templates/1877ba6e0e08d9ca44b2eca0340d438b9b7ec4f5ba2d27a8c96312d1daf3a524.png	icons_small_5e6f44225c5d66af26d432568163c0f48c756ab5e04daf0c333904bdbe541d3e20160826-27944-14je0kz		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:31	2	approved	5e6f44225c5d66af26d432568163c0f48c756ab5e04daf0c333904bdbe541d3e20160826-27944-14je0kz.png	image/png	3482	2016-08-26 14:11:39
42	\N	\N	_6	\r\n  Ketcher 07261614192D\r\n\r\n  8  9  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0031   -0.8765    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2062   -0.6630    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5906   -0.8765    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5906   -0.1620    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0031   -0.1620    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2062    0.0515    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2062    0.1620    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2062    0.8765    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  1  4  1  0      \r\n  3  5  1  0      \r\n  4  6  1  0      \r\n  6  5  1  0      \r\n  2  7  1  0      \r\n  6  8  1  0      \r\n  8  7  1  0      \r\nM  END\r\n	templates/c3aba2420b7569768676570440dd9e1992312ba8c926b5efc427e5248c4a56b6.png	icons_small_2d4185fdf804c470a5f3d53509be1d82e551c7b8aa7de5013baae5c95349948320160826-27944-bhbi0o		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:31	2	approved	2d4185fdf804c470a5f3d53509be1d82e551c7b8aa7de5013baae5c95349948320160826-27944-bhbi0o.png	image/png	3486	2016-08-26 14:11:40
133	\N	\N	_7	\r\n  Ketcher 07261614192D\r\n\r\n  5  4  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7553   -0.6169    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0415   -0.2047    0.0000 N   0  3  0  0  0  0  0  0  0  0  0  0\r\n    0.6723   -0.6184    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0386    0.6184    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7553    0.0095    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  2  5  1  0      \r\nM  CHG  1   2   1\r\nM  END\r\n	\N	icons_small_82ce1a56bff10b10321b306ac892f9c500b8a16f2a177d65cf9eec2847140dc320160830-1161-1gckvqy		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	82ce1a56bff10b10321b306ac892f9c500b8a16f2a177d65cf9eec2847140dc320160830-1161-1gckvqy.png	image/png	5746	2016-08-30 08:35:18
43	\N	\N	_7	\r\n  Ketcher 07261614192D\r\n\r\n  6  7  0  0  0  0  0  0  0  0999 V2000\r\n   -0.9923   -0.0015    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5078   -0.6678    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2765   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2750    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5093    0.6678    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9923    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  1  5  1  0      \r\n  3  6  1  0      \r\n  4  6  1  0      \r\nM  END\r\n	templates/d79f3b6116a68bf65323f7e9907730ce2d94ad97e69e78854a944a5d7f31c8e6.png	icons_small_930dc3eed96490557f3ffb8ed4bc78210ceb1a02a65388d9eab1ed0c8b774cb020160826-27944-1y248n		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	930dc3eed96490557f3ffb8ed4bc78210ceb1a02a65388d9eab1ed0c8b774cb020160826-27944-1y248n.png	image/png	3573	2016-08-26 14:11:40
45	\N	\N	_9	\r\n  Ketcher 07261614192D\r\n\r\n  8  9  0  0  0  0  0  0  0  0999 V2000\r\n    0.0000    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7842   -0.6671    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2688    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7842    0.6686    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7842    0.6671    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2688   -0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7842   -0.6686    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  1  5  1  0      \r\n  1  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  2  8  1  0      \r\nM  END\r\n	templates/57fd1e233cd507cfe53ae135d4064d808bf398bf84ecebd5a0af5a90ad51789b.png	icons_small_a4f23ea8646690eae86c28ba32e09bacc60f7766829c347b1777257e49d7b7dd20160826-27944-1v2m7dq		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	a4f23ea8646690eae86c28ba32e09bacc60f7766829c347b1777257e49d7b7dd20160826-27944-1v2m7dq.png	image/png	3697	2016-08-26 14:11:40
47	\N	\N	_11	\r\n  Ketcher 07261614192D\r\n\r\n  9 10  0  0  0  0  0  0  0  0999 V2000\r\n    0.7182   -0.6589    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2690   -1.1843    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9866    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2973    0.4047    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4555    0.1349    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2690    0.3665    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7309   -0.5063    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0275   -0.2535    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0275    1.1843    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  8  1  1  0      \r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  9  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  7  6  1  0      \r\n  8  7  1  0      \r\n  8  9  1  0      \r\nM  END\r\n	templates/294e506799f5b67a69fdc2cbb7738689e47ffdc508f0bc9f3b0728c0d6a24726.png	icons_small_e591b34ecd6550896b088d6e82f54dfeb1f2e67a0efa0c1fc166df8d4b89a70320160826-27944-7i7lpn		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	e591b34ecd6550896b088d6e82f54dfeb1f2e67a0efa0c1fc166df8d4b89a70320160826-27944-7i7lpn.png	image/png	4244	2016-08-26 14:11:37
142	\N	\N	_16	\r\n  Ketcher 07261614192D\r\n\r\n  3  2  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7145   -0.4117    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7145    0.4117    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  3  0      \r\nM  END\r\n	\N	icons_small_60eed27cb30c9d63c5750fcf2603ba012af6441b647518a9e26bc56af4e3601620160830-1161-vkey1d		2016-08-30 08:35:19	\N	2016-08-30 08:35:19	2016-11-30 09:46:37	17	approved	60eed27cb30c9d63c5750fcf2603ba012af6441b647518a9e26bc56af4e3601620160830-1161-vkey1d.png	image/png	3405	2016-08-30 08:35:19
49	\N	\N	_13	\r\n  Ketcher 07261614192D\r\n\r\n 11 12  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7172   -0.6705    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3425    0.9150    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3675   -0.1420    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3425    0.1709    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0322   -0.4536    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0322    0.4181    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8934   -0.1407    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6304   -0.6048    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1550   -1.1030    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1550    0.1039    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5778    1.1030    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  5  1  1  0      \r\n  4  2  1  0      \r\n  3  4  1  0      \r\n  5  6  1  0      \r\n  4  7  1  0      \r\n  5  8  1  0      \r\n  7  9  1  0      \r\n  8  9  1  0      \r\n  3 10  1  0      \r\n  1 10  1  0      \r\n  6 11  1  0      \r\n  2 11  1  0      \r\nM  END\r\n	templates/6656d13f6dff34c73384e161fa3334f6ede185696d14e358ccc6e3e6bdac897c.png	icons_small_697a1408b7bcb917b9716f5b6eff97af0d3ca2e8ee2b833b0b7b3edf4b83a6f020160826-27944-1bteu6m		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	697a1408b7bcb917b9716f5b6eff97af0d3ca2e8ee2b833b0b7b3edf4b83a6f020160826-27944-1bteu6m.png	image/png	4911	2016-08-26 14:11:38
50	\N	\N	_14	\r\n  Ketcher 07261614192D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n   -0.6618   -0.9255    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5833    1.0606    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3422   -0.3167    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5833    0.0915    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0937   -0.7221    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0937    0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3011   -0.3153    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8463   -1.0606    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3011   -0.4475    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8361    0.0334    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  5  1  1  0      \r\n  6  2  1  0      \r\n  4  2  1  0      \r\n  3  4  1  0      \r\n  5  6  1  0      \r\n  4  7  1  0      \r\n  5  8  1  0      \r\n  7  8  1  0      \r\n  1  9  1  0      \r\n  3 10  1  0      \r\n  9 10  1  0      \r\nM  END\r\n	templates/cb678a336481a020a538bb4134417b9740883fe16762e4f99c73583341e7a651.png	icons_small_5742f07c5cdfbb72f9466af7dc70707005d1b49da4c60f8a07055d86c90e40e720160826-27944-1ygg622		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	5742f07c5cdfbb72f9466af7dc70707005d1b49da4c60f8a07055d86c90e40e720160826-27944-1ygg622.png	image/png	4171	2016-08-26 14:11:38
134	\N	\N	_8	\r\n  Ketcher 07261614192D\r\n\r\n  5  4  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0712   -0.6170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3561   -0.2057    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3561   -0.6185    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0712   -0.2057    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3561    0.6185    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  2  5  2  0      \r\nM  END\r\n	\N	icons_small_d292b6a2e70baf0d5c60bc89a1fc0981694054627f78be06b6ef880460e0fdc820160830-1161-iob4mq		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	d292b6a2e70baf0d5c60bc89a1fc0981694054627f78be06b6ef880460e0fdc820160830-1161-iob4mq.png	image/png	3904	2016-08-30 08:35:18
52	\N	\N	_16	\r\n  Ketcher 07261614192D\r\n\r\n 12 13  0  0  0  0  0  0  0  0999 V2000\r\n   -0.8004   -0.8147    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4245    1.1391    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4859   -0.2158    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4245    0.1858    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0572   -0.6146    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0572    0.5017    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1305   -0.2144    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7432   -0.8147    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4292   -0.3444    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9719    0.1286    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4292   -1.2434    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5431    1.2434    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  5  1  1  0      \r\n  4  2  1  0      \r\n  3  4  1  0      \r\n  5  6  1  0      \r\n  4  7  1  0      \r\n  5  8  1  0      \r\n  1  9  1  0      \r\n  3 10  1  0      \r\n  9 10  1  0      \r\n  8 11  1  0      \r\n  7 11  1  0      \r\n  2 12  1  0      \r\n  6 12  1  0      \r\nM  END\r\n	templates/4296f4f348451e40557752703ec431aa247b5e43c10658c6f23228709f2d87ad.png	icons_small_a379aff09560a3c68d3bc846317b7faae4d7ae2ab13dd9a8835ff68d954a5a8920160826-27944-vogfss		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	a379aff09560a3c68d3bc846317b7faae4d7ae2ab13dd9a8835ff68d954a5a8920160826-27944-vogfss.png	image/png	4541	2016-08-26 14:11:38
53	\N	\N	_17	\r\n  Ketcher 07261614192D\r\n\r\n  7  8  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0721    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0721   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3578   -0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3578   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3578    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3578    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0721   -0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  5  7  1  0      \r\nM  END\r\n	templates/afb674e44d45ce0f536ea9328f6accafc5e6c829b02c2c3643ef670de36d2f75.png	icons_small_3d438e299e54188288a913b88114b88d95ea8e420ebee6c77ceb08017f72406d20160826-27944-aup38s		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	3d438e299e54188288a913b88114b88d95ea8e420ebee6c77ceb08017f72406d20160826-27944-aup38s.png	image/png	3628	2016-08-26 14:11:38
55	\N	\N	_19	\r\n  Ketcher 07261614192D\r\n\r\n  9 10  0  0  0  0  0  0  0  0999 V2000\r\n    0.1210   -0.4462    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6212   -0.8064    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3022   -0.3412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6212    0.0773    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1706   -0.2421    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5687    0.1269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3252    0.8064    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3022   -0.2508    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9362   -0.8064    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  7  1  0      \r\n  6  7  1  0      \r\n  6  8  1  0      \r\n  8  9  1  0      \r\n  1  9  1  0      \r\nM  END\r\n	templates/57304e05da0879c3a57865912ba73ebe24732bec0524750734f02dadf4648a7e.png	icons_small_1118adcd3a70bf3d8c370bf24d3421220c3f8dd28d13d42f85b8f47dfa98bad420160826-27944-oua7iu		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	1118adcd3a70bf3d8c370bf24d3421220c3f8dd28d13d42f85b8f47dfa98bad420160826-27944-oua7iu.png	image/png	4043	2016-08-26 14:11:39
56	\N	\N	_20	\r\n  Ketcher 07261614192D\r\n\r\n  8  9  0  0  0  0  0  0  0  0999 V2000\r\n   -1.1282    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1282   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4140   -0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3032   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3032    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4140    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1282   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1282    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  5  8  1  0      \r\nM  END\r\n	templates/1c62d9b493d77474b0ebcc59e9a397d1b52f836e0eee6fa7bdbdd2bdec5f6aa7.png	icons_small_f9750c7513a362dce46825f58fb641bbf0e25692dd7c371d33d08faa3456327020160826-27944-14f3fwq		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	f9750c7513a362dce46825f58fb641bbf0e25692dd7c371d33d08faa3456327020160826-27944-14f3fwq.png	image/png	2563	2016-08-26 14:11:39
57	\N	\N	_21	\r\n  Ketcher 07261614192D\r\n\r\n  9 10  0  0  0  0  0  0  0  0999 V2000\r\n   -1.3491    0.4116    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3491   -0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6352   -0.8253    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0801   -0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0801    0.4116    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6352    0.8253    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8640   -0.6665    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3491    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8640    0.6680    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  5  9  1  0      \r\nM  END\r\n	templates/79ba03cca9c1389bdd40ce6dc1a0d66f63c9d4f04c705e6d9fbb6182701f3b6c.png	icons_small_d33020810f58e8cce34ec91d863fdff6606d5ada085d5037a0f29d80ee1d4c0020160826-27944-9hkvwx		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	d33020810f58e8cce34ec91d863fdff6606d5ada085d5037a0f29d80ee1d4c0020160826-27944-9hkvwx.png	image/png	3590	2016-08-26 14:11:39
59	\N	\N	_23	\r\n  Ketcher 07261614192D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4297    0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4297   -0.4115    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7160   -0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0007   -0.4115    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0007    0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7160    0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7130   -0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4297   -0.4115    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4297    0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7130    0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n  5 10  1  0      \r\nM  END\r\n	templates/c28dab4304d03edde82c4808c3110d03f746f451b228dcb3f46f2c1393a0a14d.png	icons_small_d08001958b7fd166f5769e0c912303fb6010cc2a6562272cbad395c859f328a220160826-27944-1s7qkza		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	d08001958b7fd166f5769e0c912303fb6010cc2a6562272cbad395c859f328a220160826-27944-1s7qkza.png	image/png	3175	2016-08-26 14:11:39
143	\N	\N	_17	\r\n  Ketcher 07261614192D\r\n\r\n  3  2  0  0  0  0  0  0  0  0999 V2000\r\n   -0.8250    0.0036    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000   -0.0036    0.0000 N   0  3  0  0  0  0  0  0  0  0  0  0\r\n    0.8250    0.0022    0.0000 C   0  5  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  3  0      \r\nM  CHG  2   2   1   3  -1\r\nM  END\r\n	\N	icons_small_bd21c24e2af2e2d8f493613b00438c79837d51afabb36d299d39d41f5920a23d20160830-1161-1mkpfu4		2016-08-30 08:35:19	\N	2016-08-30 08:35:19	2016-11-30 09:46:37	17	approved	bd21c24e2af2e2d8f493613b00438c79837d51afabb36d299d39d41f5920a23d20160830-1161-1mkpfu4.png	image/png	3042	2016-08-30 08:35:19
61	\N	\N	_1	\r\n  Ketcher 07261614192D\r\n\r\n  3  3  0  0  0  0  0  0  0  0999 V2000\r\n   -0.3572    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3572   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3572    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  1  1  0      \r\nM  END\r\n	templates/f448eea9e010b12d35c0afe396233ae9dbf806d2f774b51640a4b9da88fcf93a.png	icons_small_2440c40b81bf308827f56d2840ddb96e84a576fd8149d546ecc484b40ea0744520160827-31934-drvh16		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	2440c40b81bf308827f56d2840ddb96e84a576fd8149d546ecc484b40ea0744520160827-31934-drvh16.png	image/png	2664	2016-08-27 20:59:12
62	\N	\N	_2	\r\n  Ketcher 07261614192D\r\n\r\n  4  4  0  0  0  0  0  0  0  0999 V2000\r\n   -0.4125    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  1  1  0      \r\nM  END\r\n	templates/10e3dad46e21d4dd4c643262e730ddcf26cb3eabeca6e6e34055a9da02651ae0.png	icons_small_f996831465fc6257eff223fd9043540117d3cb22700065a7d307f5f38d22af4920160826-27944-2omnhb		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	f996831465fc6257eff223fd9043540117d3cb22700065a7d307f5f38d22af4920160826-27944-2omnhb.png	image/png	758	2016-08-26 14:11:39
63	\N	\N	_3	\r\n  Ketcher 07261614192D\r\n\r\n  5  5  0  0  0  0  0  0  0  0999 V2000\r\n   -0.6348    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6348   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1498   -0.6674    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6348    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1498    0.6674    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  1  1  0      \r\nM  END\r\n	templates/3c0c7b8bc1cb9b83d4559c84dfac4a5fc830e1936445d7dddefb6ae15f944662.png	icons_small_c1c27cba8a984cb3cb75541b8502d8496327c9e1f32c16527d3b1279df1776c320160826-27944-1dvqemd		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	c1c27cba8a984cb3cb75541b8502d8496327c9e1f32c16527d3b1279df1776c320160826-27944-1dvqemd.png	image/png	3281	2016-08-26 14:11:39
64	\N	\N	_4	\r\n  Ketcher 07261614192D\r\n\r\n  6  6  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7145    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7145   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000   -0.8250    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7145   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7145    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000    0.8250    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  1  1  0      \r\nM  END\r\n	templates/ff34e818296d955326add0004aa20f50d56af66328189ea1fc50bcc512b9d320.png	icons_small_4c5d88fcdacb1b98a193b3496fc6b41c12a8ac9428e155453a87ae8fb5431f2420160826-27944-1d4p4ik		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	4c5d88fcdacb1b98a193b3496fc6b41c12a8ac9428e155453a87ae8fb5431f2420160826-27944-1d4p4ik.png	image/png	2783	2016-08-26 14:11:39
66	\N	\N	8 Cs	\r\n  Ketcher 07261614192D\r\n\r\n  8  8  0  0  0  0  0  0  0  0999 V2000\r\n   -0.9959    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9959   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125   -0.9959    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125   -0.9959    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9959   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9959    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125    0.9959    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125    0.9959    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  1  1  0      \r\nM  END\r\n	templates/ed75fe79c195c185a960235143e7db6b2d517edaedd8efc54f5410aee6d0a66d.png	icons_small_24bd11499d60532fdcb6c06b8de4fad49e8be6bbc6e325e574583712bda104c720160826-27944-1kdqg6c		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	24bd11499d60532fdcb6c06b8de4fad49e8be6bbc6e325e574583712bda104c720160826-27944-1kdqg6c.png	image/png	1619	2016-08-26 14:11:40
125	\N	\N	_33	\r\n  Ketcher 07261614192D\r\n\r\n 24 24  0  0  1  0  0  0  0  0999 V2000\r\n   -0.6797    0.5617    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7692    0.2465    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9681    0.0267    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5850    1.3441    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9545   -1.3619    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7547   -0.3387    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.5953    0.2336    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5704    1.0467    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4809    1.3619    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5058    0.5472    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1711   -1.0111    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9254    0.0008    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1786   -1.3425    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6393    1.1534    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9756   -0.3047    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.5953    0.3338    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0315   -0.1867    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0315   -1.0111    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9545   -0.5375    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1786   -0.5181    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1711   -0.1867    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8598    0.6038    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8527    0.3564    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6496    0.1431    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2 19  1  1      \r\n  1 17  1  0      \r\n 21  3  1  0      \r\n 22  4  1  0      \r\n 19  5  1  0      \r\n 19  6  1  0      \r\n  2  7  1  0      \r\n  2  8  1  0      \r\n  1  9  1  0      \r\n  1 10  1  0      \r\n 21 11  1  0      \r\n 17 12  1  0      \r\n 20 13  1  0      \r\n 22 23  1  0      \r\n 23 14  1  0      \r\n 17 21  1  0      \r\n 20 15  1  0      \r\n 23 20  1  1      \r\n 22 16  1  0      \r\n 17 18  1  0      \r\n 19 20  1  1      \r\n 21 22  1  0      \r\n 23 24  1  0      \r\nM  END\r\n	\N	icons_small_b17595680b6493b621d23ef3c63d8425e550a329e78399d615c6aa70eae3f1bd20160830-29185-vr62q8		2016-08-30 06:51:29	\N	2016-08-30 06:51:30	2016-11-30 09:46:36	7	approved	b17595680b6493b621d23ef3c63d8425e550a329e78399d615c6aa70eae3f1bd20160830-29185-vr62q8.png	image/png	10235	2016-08-30 06:51:29
69	\N	\N	11 Cs	\r\n  Ketcher 07261614192D\r\n\r\n 11 11  0  0  0  0  0  0  0  0999 V2000\r\n   -0.4124   -1.4358    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -1.4358    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1065   -0.9904    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4516   -0.2412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3320    0.5753    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7945    1.2021    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0027    1.4358    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7876    1.2021    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3265    0.5766    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4516   -0.2385    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1120   -0.9904    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n  1 11  1  0      \r\nM  END\r\n	templates/644c4be794f657957df75844ce87b05ce896cddd1cde5e0fd574a83dbcf9e336.png	icons_small_c59915ef470b348abe9dc99e58b2732b036e0c10103879bcdb2cef83d60a1cff20160826-27944-1rz5zin		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	c59915ef470b348abe9dc99e58b2732b036e0c10103879bcdb2cef83d60a1cff20160826-27944-1rz5zin.png	image/png	4310	2016-08-26 14:11:37
71	\N	\N	_14	\r\n  Ketcher 07261614192D\r\n\r\n 10 10  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4288    0.4114    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4288   -0.4134    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7151   -0.8254    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0005   -0.4134    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0005    0.4114    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7151    0.8254    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7131   -0.8254    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4288   -0.4134    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4288    0.4114    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7131    0.8254    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n  5 10  1  0      \r\nM  END\r\n	templates/ba4cd610976e8b712679d27f6821099ff00371fbf13fba72859d17e1a789ad1d.png	icons_small_40312f7a3ff64b85a293b6868e0cb4a487d15dd99765a8bb6bf313f5ff653f9e20160826-27944-titysh		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	40312f7a3ff64b85a293b6868e0cb4a487d15dd99765a8bb6bf313f5ff653f9e20160826-27944-titysh.png	image/png	3070	2016-08-26 14:11:38
89	\N	\N	Guanine (DNA) Nucleotide 1	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 28 30 0 0 1\r\nM  V30 BEGIN ATOM\r\nM  V30 1 N 2.341923 2.154521 0.000000 0\r\nM  V30 2 C 2.341923 1.329521 0.000000 0\r\nM  V30 3 N 1.627621 0.915427 0.000000 0\r\nM  V30 4 C 0.911839 1.329521 0.000000 0\r\nM  V30 5 C 0.911839 2.154521 0.000000 0\r\nM  V30 6 C 1.627621 2.567135 0.000000 0\r\nM  V30 7 C -0.357891 1.742021 0.000000 0\r\nM  V30 8 N 0.127497 2.409629 0.000000 0\r\nM  V30 9 O 1.627621 3.234742 0.000000 0\r\nM  V30 10 N 2.938123 0.960640 0.000000 0\r\nM  V30 11 N 0.127497 1.074413 0.000000 0\r\nM  V30 12 C -1.681490 -1.051066 0.000000 0\r\nM  V30 13 C -0.293773 -1.051066 0.000000 0\r\nM  V30 14 C 0.127497 -0.567045 0.000000 0\r\nM  V30 15 O -0.989055 -0.153064 0.000000 0\r\nM  V30 16 C -2.111529 -0.567045 0.000000 0\r\nM  V30 17 H -0.293773 -1.596245 0.000000 0\r\nM  V30 18 H -0.293773 -0.625356 0.000000 0\r\nM  V30 19 H -1.681490 -0.625356 0.000000 0\r\nM  V30 20 H 0.127497 -1.275538 0.000000 0\r\nM  V30 21 C -2.111529 0.094754 0.000000 0\r\nM  V30 22 H -2.111529 -1.275538 0.000000 0\r\nM  V30 23 O -1.681490 -1.581668 0.000000 0\r\nM  V30 24 P -1.681490 -2.408262 0.000000 0\r\nM  V30 25 O -2.500795 -2.408262 0.000000 0\r\nM  V30 26 O -1.681490 -3.234742 0.000000 0 CHG=-1\r\nM  V30 27 O -2.938123 0.094754 0.000000 0\r\nM  V30 28 O -0.847720 -2.408262 0.000000 0 CHG=-1\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 1 1 2\r\nM  V30 2 2 2 3\r\nM  V30 3 1 3 4\r\nM  V30 4 2 4 5\r\nM  V30 5 1 5 6\r\nM  V30 6 1 1 6\r\nM  V30 7 2 7 8\r\nM  V30 8 1 5 8\r\nM  V30 9 2 6 9\r\nM  V30 10 1 2 10\r\nM  V30 11 1 12 13 CFG=1\r\nM  V30 12 1 14 13 CFG=1\r\nM  V30 13 1 14 15\r\nM  V30 14 1 15 16\r\nM  V30 15 1 16 12 CFG=1\r\nM  V30 16 1 13 17\r\nM  V30 17 1 13 18\r\nM  V30 18 1 12 19\r\nM  V30 19 1 14 20\r\nM  V30 20 1 16 21\r\nM  V30 21 1 16 22\r\nM  V30 22 1 11 14\r\nM  V30 23 1 4 11\r\nM  V30 24 1 7 11\r\nM  V30 25 1 23 24\r\nM  V30 26 2 24 25\r\nM  V30 27 1 24 26\r\nM  V30 28 1 12 23\r\nM  V30 29 1 21 27\r\nM  V30 30 1 24 28\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_232402bfcaf6e9419c5798e50c6e34dc1d6b666c125dde3afdd7c98f7ec9ef1e20160830-29185-94mzaa		2016-08-30 05:19:43	\N	2016-08-30 05:19:44	2017-10-01 13:33:22	3	approved	232402bfcaf6e9419c5798e50c6e34dc1d6b666c125dde3afdd7c98f7ec9ef1e20160830-29185-94mzaa.png	image/png	6773	2016-08-30 05:19:43
153	\N	\N	tymine (DNA) nucleotide 2	thymine-nucleotide 2.mol\r\n  ChemDraw10011715212D\r\n\r\n 24 25  0  0  1  0  0  0  0  0999 V2000\r\n    0.1019    2.1899    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1019    1.3656    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5309    1.3656    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5309    2.1899    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8156    2.6022    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8156    3.3684    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.2476    0.9518    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6133    2.6022    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8156    0.9518    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9920   -1.1719    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3874   -1.1719    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8156   -0.6882    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2622   -0.2455    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4217   -0.6882    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3874   -1.7166    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9920   -1.7166    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8156   -1.3962    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4217   -0.0270    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4217   -1.3962    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9920   -2.5426    0.0000 P   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8179   -2.5426    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9920   -3.3684    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n   -2.2476   -0.0270    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1661   -2.5426    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  1  5  1  0      \r\n  5  6  2  0      \r\n  3  7  2  0      \r\n  1  8  1  0      \r\n 10 11  1  1      \r\n 12 11  1  1      \r\n 12 13  1  0      \r\n 13 14  1  0      \r\n 14 10  1  1      \r\n 11 15  1  0      \r\n 10 16  1  0      \r\n 12 17  1  0      \r\n 14 18  1  0      \r\n 14 19  1  0      \r\n  9 12  1  0      \r\n 16 20  1  0      \r\n 20 21  2  0      \r\n 20 22  1  0      \r\n 18 23  1  0      \r\n 20 24  1  0      \r\n  9  2  1  0      \r\n  9  3  1  0      \r\nM  CHG  2  22  -1  24  -1\r\nM  END\r\n	\N	icons_small_ba2a9ec14953fa99ac13649506ea2223615350dd4f3a04f7422d0fcb52ac7636		2017-10-01 13:26:45	\N	2017-10-01 13:26:46	2017-10-01 13:26:46	3	approved	ba2a9ec14953fa99ac13649506ea2223615350dd4f3a04f7422d0fcb52ac7636.png	image/png	46954	2017-10-01 13:26:46
74	\N	\N	_17	\r\n  Ketcher 07261614192D\r\n\r\n 13 13  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4301    0.1963    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4301   -0.6287    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7160   -1.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7160    0.6106    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7142   -1.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4301   -0.6287    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4301    0.1963    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7142    0.6106    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7142    1.4356    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    1.8481    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7142    1.4356    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4252   -1.8481    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4470   -1.8481    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  1  4  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n  4 11  1  0      \r\n  3 12  1  0      \r\n 12 13  1  0      \r\n  5 13  1  0      \r\nM  END\r\n	templates/3d2fc83b0b6cdf91bd706900b46afeb0a8d1f7a0792f605cb78d8f6fff91156c.png	icons_small_d51d06a3da1ac4e070f56c68497c449642d8ad0ae2dfd34a1b5868ffd70241ae20160826-27944-1g5mbz3		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	d51d06a3da1ac4e070f56c68497c449642d8ad0ae2dfd34a1b5868ffd70241ae20160826-27944-1g5mbz3.png	image/png	3308	2016-08-26 14:11:38
76	\N	\N	12 Cs	\r\n  ChemDraw08221614242D\r\n\r\n 12 12  0  0  0  0  0  0  0  0999 V2000\r\n   -0.4123   -1.5391    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4123   -1.5391    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1269   -1.1269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5391   -0.4123    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5391    0.4123    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1269    1.1269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4123    1.5391    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4123    1.5391    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1269    1.1269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5391    0.4123    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5391   -0.4123    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1269   -1.1269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n 11 12  1  0      \r\n  1 12  1  0      \r\nM  END\r\n	templates/a7e4f1fe07af65a508a3d10252cceb03e15d99a2907497bcfce8c3047a15b054.png	icons_small_f03a01a58216c65270693179fbb78790630608f23cbdd67fec1db76c9edb131d20160826-27944-81izzg		2016-08-22 12:24:37	\N	2016-08-22 12:24:37	2016-11-30 09:46:33	15	approved	f03a01a58216c65270693179fbb78790630608f23cbdd67fec1db76c9edb131d20160826-27944-81izzg.png	image/png	4102	2016-08-26 14:11:38
154	\N	\N	Aminomethyl-polystyrene	\r\n  Ketcher 10011716122D 1   1.00000     0.00000     0\r\n\r\n  3  2  0     0  0            999 V2000\r\n    5.9170   -5.1750    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.7830   -4.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.6490   -5.1750    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_046952c07b8e7bebe203eb0f1a78901cfa6411fa3c06fc31f7876cf4f00a283f		2017-10-01 14:12:31	\N	2017-10-01 14:12:31	2017-10-01 14:13:25	18	approved	046952c07b8e7bebe203eb0f1a78901cfa6411fa3c06fc31f7876cf4f00a283f.png	image/png	36560	2017-10-01 14:12:31
141	\N	\N	_15	\r\n  Ketcher 07261614192D\r\n\r\n  5  4  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7550   -0.6161    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0422   -0.2044    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6721   -0.6175    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0393    0.6175    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7550    0.0080    0.0000 F   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  2  5  1  0      \r\nM  END\r\n	\N	icons_small_cb8df35d9852b3f63b086764df4985313d0152ebc13e922f44adbb0abc7d585920160830-1161-iqa4at		2016-08-30 08:35:19	\N	2016-08-30 08:35:19	2016-11-30 09:46:37	17	approved	cb8df35d9852b3f63b086764df4985313d0152ebc13e922f44adbb0abc7d585920160830-1161-iqa4at.png	image/png	3632	2016-08-30 08:35:19
78	\N	\N	Adenine (DNA)	\r\n  ChemDraw08271621362D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n    1.3497    0.0007    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3497   -0.8243    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6355   -1.2382    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0801   -0.8243    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0801    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6355    0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8643   -1.0793    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3497   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8643    0.2558    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6355    1.2382    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  1  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  2  0      \r\n  5  9  1  0      \r\n  6 10  1  0      \r\nM  END\r\n	\N	icons_small_132cfe55b5a0054a9ff1af256b0eaf2e9c2c42e3c9490e8441a3a64a704db83620160829-29185-1n52h8		2016-08-29 12:04:23	\N	2016-08-29 12:04:23	2017-10-01 13:36:00	3	approved	132cfe55b5a0054a9ff1af256b0eaf2e9c2c42e3c9490e8441a3a64a704db83620160829-29185-1n52h8.png	image/png	5681	2016-08-29 14:09:00
79	\N	\N	Adenosine (DNA) Nucleoside	\r\n  ChemDraw08271621362D\r\n\r\n 23 25  0  0  1  0  0  0  0  0999 V2000\r\n    2.5843    1.2565    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.5843    0.4315    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8701    0.0175    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1544    0.4315    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1544    1.2565    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8701    1.6689    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3703    0.1764    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1152    0.8439    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3703    1.5115    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8701    2.4939    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4386   -1.9488    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0510   -1.9488    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3703   -1.4648    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7463   -1.0509    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8686   -1.4648    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0510   -2.4939    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4386   -2.4939    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0510   -1.5231    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4386   -1.5231    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3703   -2.1732    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8686   -0.8031    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8686   -2.1732    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.5843   -0.3892    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  1  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  2  0      \r\n  5  9  1  0      \r\n  6 10  1  0      \r\n 11 12  1  1      \r\n 13 12  1  1      \r\n 13 14  1  0      \r\n 14 15  1  0      \r\n 15 11  1  1      \r\n 12 16  1  0      \r\n 11 17  1  0      \r\n 12 18  1  0      \r\n 11 19  1  0      \r\n 13 20  1  0      \r\n 15 21  1  0      \r\n 15 22  1  0      \r\n  7 13  1  0      \r\n 21 23  1  0      \r\nM  END\r\n	\N	icons_small_e8664e248fcf9dbaf026f3633e340f62d7e5b1899d4762931ab156cabb48725120160829-25371-1l66isb		2016-08-29 12:04:24	\N	2016-08-29 12:04:24	2017-10-01 13:38:12	3	approved	e8664e248fcf9dbaf026f3633e340f62d7e5b1899d4762931ab156cabb48725120160829-25371-1l66isb.png	image/png	6897	2016-08-29 12:04:24
80	\N	\N	Adenine (DNA) Nucleotide 2	\r\n  ChemDraw08271621362D\r\n\r\n 27 29  0  0  1  0  0  0  0  0999 V2000\r\n    3.4661    1.2565    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.4661    0.4315    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.7519    0.0175    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.0362    0.4315    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.0362    1.2565    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.7519    1.6689    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2521    0.1764    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7666    0.8439    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2521    1.5115    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.7519    2.4939    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5568   -1.9488    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8309   -1.9488    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2521   -1.4648    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1735   -1.0218    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9868   -1.4648    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8309   -2.4939    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5568   -2.4939    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8309   -1.5231    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5568   -1.5231    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2521   -2.1732    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9868   -0.8031    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9868   -2.1732    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8132   -0.8031    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.6396   -0.8031    0.0000 P   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -3.4661   -0.8031    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n   -2.6396   -1.6295    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n   -2.6396    0.0175    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  1  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  2  0      \r\n  5  9  1  0      \r\n  6 10  1  0      \r\n 11 12  1  1      \r\n 13 12  1  1      \r\n 13 14  1  0      \r\n 14 15  1  0      \r\n 15 11  1  1      \r\n 12 16  1  0      \r\n 11 17  1  0      \r\n 12 18  1  0      \r\n 11 19  1  0      \r\n 13 20  1  0      \r\n 15 21  1  0      \r\n 15 22  1  0      \r\n  7 13  1  0      \r\n 21 23  1  0      \r\n 23 24  1  0      \r\n 24 25  1  0      \r\n 24 26  1  0      \r\n 24 27  2  0      \r\nM  CHG  2  25  -1  26  -1\r\nM  END\r\n	\N	icons_small_04c8a0b6bf325b4eec062a12c3442092e1b5decdee5cf31d4d6a75095c683fcf20160829-25371-s471a1		2016-08-29 12:04:24	\N	2016-08-29 12:04:24	2017-10-01 13:36:33	3	approved	04c8a0b6bf325b4eec062a12c3442092e1b5decdee5cf31d4d6a75095c683fcf20160829-25371-s471a1.png	image/png	6248	2016-08-29 12:04:24
81	\N	\N	Adenine (DNA) Nucleotide 1	\r\n  ChemDraw08271621362D\r\n\r\n 27 29  0  0  1  0  0  0  0  0999 V2000\r\n    2.6397    2.1120    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.6397    1.2870    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9255    0.8731    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2098    1.2870    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2098    2.1120    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9255    2.5245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4257    1.0320    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0598    1.6995    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4257    2.3671    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9255    3.2912    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3832   -1.0932    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0044   -1.0932    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4257   -0.6093    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6529   -0.1662    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8132   -0.6093    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0044   -1.6383    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3832   -1.6383    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0044   -0.6676    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3832   -0.6676    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4257   -1.3177    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8132    0.0524    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8132   -1.3177    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3832   -2.4647    0.0000 P   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.2097   -2.4647    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3832   -3.2912    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n   -2.6397    0.0524    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5567   -2.4647    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  1  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  2  0      \r\n  5  9  1  0      \r\n  6 10  1  0      \r\n 11 12  1  1      \r\n 13 12  1  1      \r\n 13 14  1  0      \r\n 14 15  1  0      \r\n 15 11  1  1      \r\n 12 16  1  0      \r\n 11 17  1  0      \r\n 12 18  1  0      \r\n 11 19  1  0      \r\n 13 20  1  0      \r\n 15 21  1  0      \r\n 15 22  1  0      \r\n  7 13  1  0      \r\n 17 23  1  0      \r\n 23 24  2  0      \r\n 23 25  1  0      \r\n 21 26  1  0      \r\n 23 27  1  0      \r\nM  CHG  2  25  -1  27  -1\r\nM  END\r\n	\N	icons_small_e53271e6df9468e8080f7cca0011c39874a900c859e1379bf96f4b75e9408f6420160829-25371-1llq4qv		2016-08-29 12:04:24	\N	2016-08-29 12:04:24	2017-10-01 13:36:18	3	approved	e53271e6df9468e8080f7cca0011c39874a900c859e1379bf96f4b75e9408f6420160829-25371-1llq4qv.png	image/png	6315	2016-08-29 12:04:24
82	\N	\N	Cytosine (DNA)	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 8 8 0 0 0\r\nM  V30 BEGIN ATOM\r\nM  V30 1 N 0.356211 0.029874 0.000000 0\r\nM  V30 2 C 0.356211 -0.794646 0.000000 0\r\nM  V30 3 N -0.357576 -1.208328 0.000000 0\r\nM  V30 4 C -1.072843 -0.794646 0.000000 0\r\nM  V30 5 C -1.072843 0.029874 0.000000 0\r\nM  V30 6 C -0.357576 0.442076 0.000000 0\r\nM  V30 7 N -0.357576 1.208328 0.000000 0\r\nM  V30 8 O 1.072843 -1.208328 0.000000 0\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 1 1 2\r\nM  V30 2 1 2 3\r\nM  V30 3 1 3 4\r\nM  V30 4 2 4 5\r\nM  V30 5 1 5 6\r\nM  V30 6 2 1 6\r\nM  V30 7 1 6 7\r\nM  V30 8 2 2 8\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_93301424f75e9f9ac901395ae90a98a01e7d0c55802f2b31e1a10d0bfd37c05320160830-29185-iyfxiv		2016-08-30 05:18:18	\N	2016-08-30 05:18:18	2017-10-01 13:35:37	3	approved	93301424f75e9f9ac901395ae90a98a01e7d0c55802f2b31e1a10d0bfd37c05320160830-29185-iyfxiv.png	image/png	4723	2016-08-30 05:18:39
155	\N	\N	Merrifield resin	\r\n  Ketcher 10011716122D 1   1.00000     0.00000     0\r\n\r\n  3  2  0     0  0            999 V2000\r\n    5.5670   -5.3250    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.4330   -4.8250    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.2990   -5.3250    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_970b987092662f59e54170c69ab9723890a74da6d7b2acdf8ceb05246112cb38		2017-10-01 14:13:07	\N	2017-10-01 14:13:07	2017-10-01 14:13:07	18	approved	970b987092662f59e54170c69ab9723890a74da6d7b2acdf8ceb05246112cb38.png	image/png	36549	2017-10-01 14:13:06
84	\N	\N	Cytosine (DNA) Nucleotide 2	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 25 26 0 0 1\r\nM  V30 BEGIN ATOM\r\nM  V30 1 C 0.929136 1.364979 0.000000 0\r\nM  V30 2 C 0.929136 0.539979 0.000000 0\r\nM  V30 3 C 2.359022 0.539979 0.000000 0\r\nM  V30 4 N 2.359022 1.364979 0.000000 0\r\nM  V30 5 C 1.643339 1.777536 0.000000 0\r\nM  V30 6 N 1.643339 2.544120 0.000000 0\r\nM  V30 7 O 3.074705 0.126056 0.000000 0\r\nM  V30 8 N 1.643339 0.126056 0.000000 0\r\nM  V30 9 C -0.165399 -1.999017 0.000000 0\r\nM  V30 10 C 1.222127 -1.999017 0.000000 0\r\nM  V30 11 C 1.643339 -1.515176 0.000000 0\r\nM  V30 12 O 0.564747 -1.071988 0.000000 0\r\nM  V30 13 C -0.595378 -1.515176 0.000000 0\r\nM  V30 14 H 1.222127 -2.544120 0.000000 0\r\nM  V30 15 O -0.165399 -2.544120 0.000000 0\r\nM  V30 16 H 1.222127 -1.573478 0.000000 0\r\nM  V30 17 H -0.165399 -1.573478 0.000000 0\r\nM  V30 18 H 1.643339 -2.223457 0.000000 0\r\nM  V30 19 C -0.595378 -0.853354 0.000000 0\r\nM  V30 20 H -0.595378 -2.223457 0.000000 0\r\nM  V30 21 O -1.421858 -0.853354 0.000000 0\r\nM  V30 22 P -2.248339 -0.853354 0.000000 0\r\nM  V30 23 O -3.074705 -0.853354 0.000000 0 CHG=-1\r\nM  V30 24 O -2.248339 -1.679834 0.000000 0 CHG=-1\r\nM  V30 25 O -2.248339 -0.032795 0.000000 0\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 2 1 2\r\nM  V30 2 1 3 4\r\nM  V30 3 2 4 5\r\nM  V30 4 1 1 5\r\nM  V30 5 1 5 6\r\nM  V30 6 2 3 7\r\nM  V30 7 1 9 10 CFG=1\r\nM  V30 8 1 11 10 CFG=1\r\nM  V30 9 1 11 12\r\nM  V30 10 1 12 13\r\nM  V30 11 1 13 9 CFG=1\r\nM  V30 12 1 10 14\r\nM  V30 13 1 9 15\r\nM  V30 14 1 10 16\r\nM  V30 15 1 9 17\r\nM  V30 16 1 11 18\r\nM  V30 17 1 13 19\r\nM  V30 18 1 13 20\r\nM  V30 19 1 8 11\r\nM  V30 20 1 19 21\r\nM  V30 21 1 21 22\r\nM  V30 22 1 22 23\r\nM  V30 23 1 22 24\r\nM  V30 24 2 22 25\r\nM  V30 25 1 8 2\r\nM  V30 26 1 8 3\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_7ffe394f7e88dc1bc76f3c37494f3359844c7cb9bc78802f0e7d91bfc383137820160830-29185-xh3vnv		2016-08-30 05:18:18	\N	2016-08-30 05:18:18	2017-10-01 13:32:15	3	approved	7ffe394f7e88dc1bc76f3c37494f3359844c7cb9bc78802f0e7d91bfc383137820160830-29185-xh3vnv.png	image/png	6034	2016-08-30 05:18:18
85	\N	\N	Cytosine (DNA) Nucleotide 1	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 25 26 0 0 1\r\nM  V30 BEGIN ATOM\r\nM  V30 1 C 0.102759 2.189918 0.000000 0\r\nM  V30 2 C 0.102759 1.365570 0.000000 0\r\nM  V30 3 C 1.531714 1.365570 0.000000 0\r\nM  V30 4 N 1.531714 2.189918 0.000000 0\r\nM  V30 5 C 0.816496 2.602206 0.000000 0\r\nM  V30 6 N 0.816496 3.368405 0.000000 0\r\nM  V30 7 O 2.246817 0.951802 0.000000 0\r\nM  V30 8 N 0.816496 0.951802 0.000000 0\r\nM  V30 9 C -0.991176 -1.171886 0.000000 0\r\nM  V30 10 C 0.395560 -1.171886 0.000000 0\r\nM  V30 11 C 0.816496 -0.688247 0.000000 0\r\nM  V30 12 O -0.261393 -0.245461 0.000000 0\r\nM  V30 13 C -1.420875 -0.688247 0.000000 0\r\nM  V30 14 H 0.395560 -1.716635 0.000000 0\r\nM  V30 15 O -0.991176 -1.716635 0.000000 0\r\nM  V30 16 H 0.395560 -0.746512 0.000000 0\r\nM  V30 17 H -0.991176 -0.746512 0.000000 0\r\nM  V30 18 H 0.816496 -1.396181 0.000000 0\r\nM  V30 19 C -1.420875 -0.026970 0.000000 0\r\nM  V30 20 H -1.420875 -1.396181 0.000000 0\r\nM  V30 21 P -0.991176 -2.542577 0.000000 0\r\nM  V30 22 O -1.817118 -2.542577 0.000000 0\r\nM  V30 23 O -0.991176 -3.368405 0.000000 0 CHG=-1\r\nM  V30 24 O -2.246817 -0.026970 0.000000 0\r\nM  V30 25 O -0.165234 -2.542577 0.000000 0 CHG=-1\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 2 1 2\r\nM  V30 2 1 3 4\r\nM  V30 3 2 4 5\r\nM  V30 4 1 1 5\r\nM  V30 5 1 5 6\r\nM  V30 6 2 3 7\r\nM  V30 7 1 9 10 CFG=1\r\nM  V30 8 1 11 10 CFG=1\r\nM  V30 9 1 11 12\r\nM  V30 10 1 12 13\r\nM  V30 11 1 13 9 CFG=1\r\nM  V30 12 1 10 14\r\nM  V30 13 1 9 15\r\nM  V30 14 1 10 16\r\nM  V30 15 1 9 17\r\nM  V30 16 1 11 18\r\nM  V30 17 1 13 19\r\nM  V30 18 1 13 20\r\nM  V30 19 1 8 11\r\nM  V30 20 1 15 21\r\nM  V30 21 2 21 22\r\nM  V30 22 1 21 23\r\nM  V30 23 1 19 24\r\nM  V30 24 1 21 25\r\nM  V30 25 1 8 2\r\nM  V30 26 1 8 3\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_1be469ebab8fdf2ad977067c9ffc6024549056beff6f5ebfe45f75bd2213a00e20160830-29185-13cc1ca		2016-08-30 05:18:18	\N	2016-08-30 05:18:18	2017-10-01 13:34:04	3	approved	1be469ebab8fdf2ad977067c9ffc6024549056beff6f5ebfe45f75bd2213a00e20160830-29185-13cc1ca.png	image/png	5765	2016-08-30 05:18:18
86	\N	\N	Guanine (DNA)	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 11 12 0 0 0\r\nM  V30 BEGIN ATOM\r\nM  V30 1 N 0.990840 0.000740 0.000000 0\r\nM  V30 2 C 0.990840 -0.823964 0.000000 0\r\nM  V30 3 N 0.276893 -1.237739 0.000000 0\r\nM  V30 4 C -0.438533 -0.823964 0.000000 0\r\nM  V30 5 C -0.438533 0.000740 0.000000 0\r\nM  V30 6 C 0.276893 0.413035 0.000000 0\r\nM  V30 7 N -1.222486 -1.078945 0.000000 0\r\nM  V30 8 C -1.707633 -0.411669 0.000000 0\r\nM  V30 9 N -1.222486 0.255721 0.000000 0\r\nM  V30 10 O 0.276893 1.237739 0.000000 0\r\nM  V30 11 N 1.707633 -1.237739 0.000000 0\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 1 1 2\r\nM  V30 2 2 2 3\r\nM  V30 3 1 3 4\r\nM  V30 4 2 4 5\r\nM  V30 5 1 5 6\r\nM  V30 6 1 1 6\r\nM  V30 7 1 4 7\r\nM  V30 8 1 7 8\r\nM  V30 9 2 8 9\r\nM  V30 10 1 5 9\r\nM  V30 11 2 6 10\r\nM  V30 12 1 2 11\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_e3819aa3c4ccec79b5c19781fe1b2fa823e36e49f9c56dd6b23342e4461813a420160830-29185-1fdcx6a		2016-08-30 05:19:43	\N	2016-08-30 05:19:43	2017-10-01 13:31:36	3	approved	e3819aa3c4ccec79b5c19781fe1b2fa823e36e49f9c56dd6b23342e4461813a420160830-29185-1fdcx6a.png	image/png	5393	2016-08-30 05:24:52
87	\N	\N	Guanine (DNA) Nucleoside (Guanosine)	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 24 26 0 0 1\r\nM  V30 BEGIN ATOM\r\nM  V30 1 N 2.225678 1.256460 0.000000 0\r\nM  V30 2 C 2.225678 0.431460 0.000000 0\r\nM  V30 3 N 1.511475 0.017536 0.000000 0\r\nM  V30 4 C 0.795792 0.431460 0.000000 0\r\nM  V30 5 C 0.795792 1.256460 0.000000 0\r\nM  V30 6 C 1.511475 1.668903 0.000000 0\r\nM  V30 7 C -0.473763 0.843903 0.000000 0\r\nM  V30 8 N 0.011672 1.511532 0.000000 0\r\nM  V30 9 O 1.511475 2.493903 0.000000 0\r\nM  V30 10 N 2.942842 0.017536 0.000000 0\r\nM  V30 11 N 0.011672 0.176387 0.000000 0\r\nM  V30 12 C -1.797179 -1.948799 0.000000 0\r\nM  V30 13 C -0.409539 -1.948799 0.000000 0\r\nM  V30 14 C 0.011672 -1.464845 0.000000 0\r\nM  V30 15 O -1.104839 -1.050921 0.000000 0\r\nM  V30 16 C -2.227158 -1.464845 0.000000 0\r\nM  V30 17 H -0.409539 -2.493903 0.000000 0\r\nM  V30 18 O -1.797179 -2.493903 0.000000 0\r\nM  V30 19 H -0.409539 -1.523147 0.000000 0\r\nM  V30 20 H -1.797179 -1.523147 0.000000 0\r\nM  V30 21 H 0.011672 -2.173240 0.000000 0\r\nM  V30 22 C -2.227158 -0.803137 0.000000 0\r\nM  V30 23 H -2.227158 -2.173240 0.000000 0\r\nM  V30 24 O -2.942842 -0.389213 0.000000 0\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 1 1 2\r\nM  V30 2 2 2 3\r\nM  V30 3 1 3 4\r\nM  V30 4 2 4 5\r\nM  V30 5 1 5 6\r\nM  V30 6 1 1 6\r\nM  V30 7 2 7 8\r\nM  V30 8 1 5 8\r\nM  V30 9 2 6 9\r\nM  V30 10 1 2 10\r\nM  V30 11 1 12 13 CFG=1\r\nM  V30 12 1 14 13 CFG=1\r\nM  V30 13 1 14 15\r\nM  V30 14 1 15 16\r\nM  V30 15 1 16 12 CFG=1\r\nM  V30 16 1 13 17\r\nM  V30 17 1 12 18\r\nM  V30 18 1 13 19\r\nM  V30 19 1 12 20\r\nM  V30 20 1 14 21\r\nM  V30 21 1 16 22\r\nM  V30 22 1 16 23\r\nM  V30 23 1 11 14\r\nM  V30 24 1 22 24\r\nM  V30 25 1 4 11\r\nM  V30 26 1 7 11\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_4dbb7ba7d3fb888baef0969acf9b1de6f425afdb5c48ccb1520b2ab6fc2577c220160830-29185-1wr11jc		2016-08-30 05:19:43	\N	2016-08-30 05:19:43	2017-10-01 13:32:48	3	approved	4dbb7ba7d3fb888baef0969acf9b1de6f425afdb5c48ccb1520b2ab6fc2577c220160830-29185-1wr11jc.png	image/png	6492	2016-08-30 05:19:43
88	\N	\N	Guanine (DNA) Nucleotide 2	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 28 30 0 0 1\r\nM  V30 BEGIN ATOM\r\nM  V30 1 N 3.107557 1.256346 0.000000 0\r\nM  V30 2 C 3.107557 0.431460 0.000000 0\r\nM  V30 3 N 2.393354 0.017422 0.000000 0\r\nM  V30 4 C 1.677671 0.431460 0.000000 0\r\nM  V30 5 C 1.677671 1.256346 0.000000 0\r\nM  V30 6 C 2.393354 1.668903 0.000000 0\r\nM  V30 7 C 0.408116 0.843903 0.000000 0\r\nM  V30 8 N 0.893437 1.511418 0.000000 0\r\nM  V30 9 O 2.393354 2.493903 0.000000 0\r\nM  V30 10 N 3.824607 0.017422 0.000000 0\r\nM  V30 11 N 0.893437 0.176387 0.000000 0\r\nM  V30 12 C -0.915300 -1.948799 0.000000 0\r\nM  V30 13 C 0.472226 -1.948799 0.000000 0\r\nM  V30 14 C 0.893437 -1.464845 0.000000 0\r\nM  V30 15 O -0.222961 -1.050921 0.000000 0\r\nM  V30 16 C -1.345280 -1.464845 0.000000 0\r\nM  V30 17 H 0.472226 -2.493903 0.000000 0\r\nM  V30 18 H 0.472226 -1.523147 0.000000 0\r\nM  V30 19 H -0.915300 -1.523147 0.000000 0\r\nM  V30 20 H 0.893437 -2.173240 0.000000 0\r\nM  V30 21 C -1.345280 -0.803137 0.000000 0\r\nM  V30 22 H -1.345280 -2.173240 0.000000 0\r\nM  V30 23 O -0.915300 -2.479327 0.000000 0\r\nM  V30 24 O -2.171760 -0.803137 0.000000 0\r\nM  V30 25 P -2.998240 -0.803137 0.000000 0\r\nM  V30 26 O -3.824607 -0.803137 0.000000 0 CHG=-1\r\nM  V30 27 O -2.998240 0.017422 0.000000 0\r\nM  V30 28 O -2.998240 -1.629617 0.000000 0 CHG=-1\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 1 1 2\r\nM  V30 2 2 2 3\r\nM  V30 3 1 3 4\r\nM  V30 4 2 4 5\r\nM  V30 5 1 5 6\r\nM  V30 6 1 1 6\r\nM  V30 7 2 7 8\r\nM  V30 8 1 5 8\r\nM  V30 9 2 6 9\r\nM  V30 10 1 2 10\r\nM  V30 11 1 12 13 CFG=1\r\nM  V30 12 1 14 13 CFG=1\r\nM  V30 13 1 14 15\r\nM  V30 14 1 15 16\r\nM  V30 15 1 16 12 CFG=1\r\nM  V30 16 1 13 17\r\nM  V30 17 1 13 18\r\nM  V30 18 1 12 19\r\nM  V30 19 1 14 20\r\nM  V30 20 1 16 21\r\nM  V30 21 1 16 22\r\nM  V30 22 1 11 14\r\nM  V30 23 1 4 11\r\nM  V30 24 1 7 11\r\nM  V30 25 1 12 23\r\nM  V30 26 1 21 24\r\nM  V30 27 1 24 25\r\nM  V30 28 1 25 26\r\nM  V30 29 2 25 27\r\nM  V30 30 1 25 28\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_ff4a67304e647649f4ae64868c3eb1129b135e14b860c409fe1f5b5a6866111720160830-29185-brszo1		2016-08-30 05:19:43	\N	2016-08-30 05:19:43	2017-10-01 13:33:05	3	approved	ff4a67304e647649f4ae64868c3eb1129b135e14b860c409fe1f5b5a6866111720160830-29185-brszo1.png	image/png	5566	2016-08-30 05:19:43
139	\N	\N	_13	\r\n  Ketcher 07261614192D\r\n\r\n  5  4  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7138   -0.5635    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0007   -0.1510    0.0000 S   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7138   -0.5635    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4117    0.5635    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4132    0.5635    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  2  0      \r\n  2  5  2  0      \r\nM  END\r\n	\N	icons_small_81f536c1efe053955ff59aaba53611baa9bc93177a942b1e0368caaea1868bb120160830-1161-v4suxx		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	81f536c1efe053955ff59aaba53611baa9bc93177a942b1e0368caaea1868bb120160830-1161-v4suxx.png	image/png	5407	2016-08-30 08:35:18
91	\N	\N	Paracyclophane 1b	\r\n  Ketcher 05191712582D 1   1.00000     0.00000     0\r\n\r\n 16 18  0     0  0            999 V2000\r\n    0.5525    1.6412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1082    1.1377    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5525    0.5231    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5590    0.5231    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1148    1.1377    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5590    1.6412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5525   -0.3269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0690   -0.8500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5525   -1.4450    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5590   -1.4450    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1148   -0.8303    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5590   -0.3269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3241   -0.4381    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3241   -2.0204    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3241    2.0204    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3241    0.4381    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0     0  0\r\n  2  3  1  1     0  0\r\n  3  4  2  0     0  0\r\n  5  4  1  1     0  0\r\n  5  6  2  0     0  0\r\n  6  1  1  0     0  0\r\n  7  8  2  0     0  0\r\n  8  9  1  1     0  0\r\n  9 10  2  0     0  0\r\n 11 10  1  1     0  0\r\n 11 12  2  0     0  0\r\n 12  7  1  0     0  0\r\n  3 13  1  1     0  0\r\n  9 14  1  1     0  0\r\n  6 15  1  0     0  0\r\n 12 16  1  0     0  0\r\n 16 15  1  0     0  0\r\n 14 13  1  1     0  0\r\nM  END\r\n> <BoldBondsList>\r\n12 13 17\r\n$$$$\r\n\r\n	\N	icons_small_622b2a097148213a746b277e9ad954df28478d6e0d2cd91c159eba90ef03e2a2		2016-08-30 06:15:56	\N	2016-08-30 06:15:56	2017-05-19 10:58:32	14	approved	622b2a097148213a746b277e9ad954df28478d6e0d2cd91c159eba90ef03e2a2.png	image/png	38586	2017-05-19 10:58:31
92	\N	\N	Paracyclophane 3	\r\n  Ketcher 10071615462D 1   1.00000     0.00000     0\r\n\r\n 16 18  0     0  0            999 V2000\r\n   -1.9549    0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.9549   -0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2516   -0.8121    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5483   -0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5483    0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2516    0.8121    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5483    0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5483   -0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2516   -0.8121    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9549   -0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9549    0.4061    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2516    0.8121    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2516    1.6242    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2516    1.6242    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2516   -1.6242    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2516   -1.6242    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0     0  0\r\n  2  3  1  0     0  0\r\n  3  4  2  0     0  0\r\n  4  5  1  0     0  0\r\n  5  6  2  0     0  0\r\n  6  1  1  0     0  0\r\n  7  8  2  0     0  0\r\n  8  9  1  0     0  0\r\n  9 10  2  0     0  0\r\n 10 11  1  0     0  0\r\n 11 12  2  0     0  0\r\n 12  7  1  0     0  0\r\n  6 13  1  0     0  0\r\n 12 14  1  0     0  0\r\n  3 15  1  0     0  0\r\n  9 16  1  0     0  0\r\n 15 16  1  0     0  0\r\n 14 13  1  0     0  0\r\nM  END\r\n	\N	icons_small_3a01e9f4346b97367b4b9c77a381dc434779f7061ff7e493b67a9ab502315ff720161007-4199-1e902pt		2016-08-30 06:15:56	\N	2016-08-30 06:15:56	2016-11-30 09:46:34	14	approved	3a01e9f4346b97367b4b9c77a381dc434779f7061ff7e493b67a9ab502315ff720161007-4199-1e902pt.png	image/png	966	2016-10-07 13:46:13
93	\N	\N	Paracyclophane 2	\r\n  ChemDraw08301608152D\r\n\r\n 16 18  0  0  0  0  0  0  0  0999 V2000\r\n    0.4312    1.7802    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3938    1.7802    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8063    1.0658    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3938    0.3513    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4312    0.3513    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8437    1.0658    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4312   -0.3513    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3938   -0.3513    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8063   -1.0658    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3938   -1.7802    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4312   -1.7802    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8437   -1.0658    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4069    0.6170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4069   -0.5422    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4069    0.6170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4069   -0.5422    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  6  1  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n 10 11  1  0      \r\n 11 12  2  0      \r\n 12  7  1  0      \r\n  6 13  1  0      \r\n 12 14  1  0      \r\n  3 15  1  0      \r\n  9 16  1  0      \r\n 15 16  1  0      \r\n 14 13  1  0      \r\nM  END\r\n	\N	icons_small_8cc460f3f3f70711c3a5f5018f070d901a6f73404e3a12ff528c987ba386a3a520160830-29185-165wo6r		2016-08-30 06:15:56	\N	2016-08-30 06:15:56	2016-11-30 09:46:34	14	approved	8cc460f3f3f70711c3a5f5018f070d901a6f73404e3a12ff528c987ba386a3a520160830-29185-165wo6r.png	image/png	5482	2016-08-30 06:15:56
97	\N	\N	_5	\r\n  Ketcher 07261614192D\r\n\r\n 14 13  0  0  0  0  0  0  0  0999 V2000\r\n   -0.0000    0.9446    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3778    0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3778    0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3778    0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3778    0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3778   -0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3778   -0.1889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3778   -0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3778   -0.5668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.9446    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  2  5  1  0      \r\n  5  6  1  0      \r\n  5  7  1  0      \r\n  5  8  1  0      \r\n  6  9  1  0      \r\n  6 10  1  0      \r\n  6 11  1  0      \r\n  9 12  1  0      \r\n  9 13  1  0      \r\n  9 14  1  0      \r\nM  END\r\n	\N	icons_small_7d0796cd590cabf6fce366f62dc564a46d15aa73c8b460c4a61b37e9e923418820160830-29185-1oxtj2c		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	7d0796cd590cabf6fce366f62dc564a46d15aa73c8b460c4a61b37e9e923418820160830-29185-1oxtj2c.png	image/png	6495	2016-08-30 06:51:27
98	\N	\N	_6	\r\n  Ketcher 07261614192D\r\n\r\n  8  7  0  0  0  0  0  0  0  0999 V2000\r\n    0.4164   -0.1382    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4164   -0.6224    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0033   -0.8646    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8351   -0.8646    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4164    0.8646    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4164    0.3803    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8351    0.1382    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0033    0.1382    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  6  8  1  0      \r\n  2  6  1  0      \r\nM  END\r\n	\N	icons_small_186c44edd64824308ea84910d2c1d4a99b32fc6c159b54399d14676492cc68dc20160830-29185-1vvlfix		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	186c44edd64824308ea84910d2c1d4a99b32fc6c159b54399d14676492cc68dc20160830-29185-1vvlfix.png	image/png	7099	2016-08-30 06:51:27
99	\N	\N	_7	\r\n  Ketcher 07261614192D\r\n\r\n  8  7  0  0  0  0  0  0  0  0999 V2000\r\n    0.4264   -0.0171    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4264   -0.5014    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0076   -0.7435    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8461   -0.7435    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4264    0.0171    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0076    0.7435    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8461    0.7435    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4264    0.5014    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  2  8  1  0      \r\n  8  5  1  0      \r\n  8  6  1  0      \r\n  7  8  1  0      \r\nM  END\r\n	\N	icons_small_d667f7551af6ec533640d49ddbec9688881f9c35118777704678eacded1980f120160830-29185-cwka7b		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	d667f7551af6ec533640d49ddbec9688881f9c35118777704678eacded1980f120160830-29185-cwka7b.png	image/png	7372	2016-08-30 06:51:27
100	\N	\N	_8	\r\n  Ketcher 07261614192D\r\n\r\n  9  9  0  0  1  0  0  0  0  0999 V2000\r\n   -0.0423   -0.1727    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8216    0.1708    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8216    0.1708    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8216    0.6551    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8216   -0.3125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0423    0.3116    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0423   -0.6551    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8216    0.6551    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8216   -0.3125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  2  1  1  1      \r\n  2  3  1  0      \r\n  3  1  1  1      \r\n  2  4  1  0      \r\n  2  5  1  0      \r\n  1  6  1  0      \r\n  1  7  1  0      \r\n  3  8  1  0      \r\n  3  9  1  0      \r\nM  END\r\n	\N	icons_small_0c21f475f4ffe4700c07b795ddbed871944050bdc2f73263541bd2fc27eee3de20160830-29185-bz9yds		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	0c21f475f4ffe4700c07b795ddbed871944050bdc2f73263541bd2fc27eee3de20160830-29185-bz9yds.png	image/png	6783	2016-08-30 06:51:27
101	\N	\N	_9	\r\n  Ketcher 07261614192D\r\n\r\n  9  9  0  0  1  0  0  0  0  0999 V2000\r\n   -0.6850    0.1360    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7183    0.1360    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9322    0.5495    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8723   -0.3023    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0195   -0.5704    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9322    0.5704    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9322   -0.3023    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0195   -0.1578    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0195    0.2557    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  8  1  1      \r\n  1  2  1  0      \r\n  2  8  1  1      \r\n  1  3  1  0      \r\n  1  4  1  0      \r\n  8  5  1  0      \r\n  2  6  1  0      \r\n  2  7  1  0      \r\n  8  9  1  0      \r\nM  END\r\n	\N	icons_small_d81a986b256ca4dd9dfab64b8a5cf6007f6d8a7ae2b912427aef2a17dffab57e20160830-29185-162xyis		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	d81a986b256ca4dd9dfab64b8a5cf6007f6d8a7ae2b912427aef2a17dffab57e20160830-29185-162xyis.png	image/png	6464	2016-08-30 06:51:27
156	\N	\N	Sulfonyl chloride resin	\r\n  Ketcher 10011716152D 1   1.00000     0.00000     0\r\n\r\n  5  4  0     0  0            999 V2000\r\n    4.5170   -4.1000    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.7580   -4.1250    0.0000 S   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.7492   -3.0841    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.7580   -5.1250    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.7580   -4.1250    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  2  0     0  0\r\n  2  4  2  0     0  0\r\n  2  5  1  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_4c03abf0e85f9ed68dba72b16da8a9dc0856d2e854981d0c2994b9f3dc3c70d6		2017-10-01 14:15:11	\N	2017-10-01 14:15:11	2017-10-01 14:19:18	18	approved	4c03abf0e85f9ed68dba72b16da8a9dc0856d2e854981d0c2994b9f3dc3c70d6.png	image/png	41218	2017-10-01 14:15:11
103	\N	\N	_11	\r\n  Ketcher 07261614192D\r\n\r\n 12 12  0  0  1  0  0  0  0  0999 V2000\r\n   -0.9987    0.3053    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0902    0.0375    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9987    0.8766    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9842    0.8766    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4771    0.0140    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4771   -0.0084    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0443   -0.8766    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4711    0.4039    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6111   -0.2246    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0902   -0.5305    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0443   -0.3053    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9842    0.3053    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1 11  1  1      \r\n  1  2  1  0      \r\n 12  2  1  0      \r\n  1  3  1  0      \r\n 12  4  1  0      \r\n 12  5  1  0      \r\n  1  6  1  0      \r\n 11  7  1  0      \r\n  2  8  1  0      \r\n 11  9  1  0      \r\n  2 10  1  0      \r\n 12 11  1  1      \r\nM  END\r\n	\N	icons_small_992618a28997fb386541ef1c40c006eff14fcb35d249195d943ee309ae52edee20160830-29185-15oinno		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	992618a28997fb386541ef1c40c006eff14fcb35d249195d943ee309ae52edee20160830-29185-15oinno.png	image/png	7292	2016-08-30 06:51:27
105	\N	\N	_13	\r\n  Ketcher 07261614192D\r\n\r\n  5  5  0  0  1  0  0  0  0  0999 V2000\r\n    0.3443    0.1694    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3452    0.1694    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5582   -0.0403    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0004   -0.1694    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5582   -0.0403    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  1      \r\n  5  4  1  1      \r\n  1  5  1  0      \r\nM  END\r\n	\N	icons_small_1f1c719fc8489b8c872dece6a59e92bc3b39b7d60a199bff09e46d1d6b79bbbd20160830-29185-chsduz		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2016-11-30 09:46:35	7	approved	1f1c719fc8489b8c872dece6a59e92bc3b39b7d60a199bff09e46d1d6b79bbbd20160830-29185-chsduz.png	image/png	1979	2016-08-30 06:51:28
106	\N	\N	_14	\r\n  Ketcher 07261614192D\r\n\r\n 15 15  0  0  1  0  0  0  0  0999 V2000\r\n   -0.6951    0.3518    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1230    0.5025    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1230   -0.5665    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1230    0.5025    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1230   -0.6852    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6951    0.8984    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6921    0.8984    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0008    0.2482    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6951   -0.0700    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1230   -0.0700    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1230   -0.0700    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6921    0.3518    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6921   -0.0700    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0008   -0.3731    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0008   -0.8984    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n 12  1  1  0      \r\n  1 11  1  0      \r\n 12 10  1  0      \r\n 10  2  1  0      \r\n 10  3  1  0      \r\n 11  4  1  0      \r\n 11  5  1  0      \r\n  1  6  1  0      \r\n 12  7  1  0      \r\n 14  8  1  0      \r\n  1  9  1  0      \r\n 10 14  1  1      \r\n 11 14  1  1      \r\n 12 13  1  0      \r\n 14 15  1  0      \r\nM  END\r\n	\N	icons_small_ddcda057d56e6f701401996fd9ff07937d52e12d8d28eaa96b510274e0806bae20160830-29185-175anfg		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2016-11-30 09:46:35	7	approved	ddcda057d56e6f701401996fd9ff07937d52e12d8d28eaa96b510274e0806bae20160830-29185-175anfg.png	image/png	8854	2016-08-30 06:51:28
135	\N	\N	_9	\r\n  Ketcher 07261614192D\r\n\r\n  6  5  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0712   -0.2042    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3561    0.2071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3561   -0.2057    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0712    0.2071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3561    1.0313    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3561   -1.0313    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  2  5  2  0      \r\n  3  6  1  0      \r\nM  END\r\n	\N	icons_small_8b9d76fa42b27e0b0f0d346658203899728b9e011687738b7428d64ab7f8d64f20160830-1161-1n819he		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	8b9d76fa42b27e0b0f0d346658203899728b9e011687738b7428d64ab7f8d64f20160830-1161-1n819he.png	image/png	4614	2016-08-30 08:35:18
157	\N	\N	2-Chlorotrityl resin	\r\n  Ketcher 10011716182D 1   1.00000     0.00000     0\r\n\r\n 22 24  0     0  0            999 V2000\r\n    4.1920   -5.3250    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.2080   -5.3500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.7080   -4.4840    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.7080   -4.4840    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.2080   -5.3500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.7080   -6.2160    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.7080   -6.2160    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.2080   -5.3500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.2080   -6.3410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.2080   -4.4090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.3580   -5.4090    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.3420   -3.9090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.3420   -2.9090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.2080   -2.4089    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.0741   -2.9090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.0741   -3.9090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.0741   -6.8410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.0741   -7.8410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.2080   -8.3411    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.3420   -7.8410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.3420   -6.8410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.9401   -6.3410    0.0000 Cl  0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  3  4  2  0     0  0\r\n  4  5  1  0     0  0\r\n  5  6  2  0     0  0\r\n  6  7  1  0     0  0\r\n  7  2  2  0     0  0\r\n  5  8  1  0     0  0\r\n  8  9  1  0     0  0\r\n  8 10  1  0     0  0\r\n  8 11  1  0     0  0\r\n 10 12  1  0     0  0\r\n 12 13  2  0     0  0\r\n 13 14  1  0     0  0\r\n 14 15  2  0     0  0\r\n 15 16  1  0     0  0\r\n 16 10  2  0     0  0\r\n  9 17  1  0     0  0\r\n 17 18  2  0     0  0\r\n 18 19  1  0     0  0\r\n 19 20  2  0     0  0\r\n 20 21  1  0     0  0\r\n 21  9  2  0     0  0\r\n 17 22  1  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_dffbf915cc7199dba01a13d2d50dbea4f8c8a8bfdd68bd92f42e2c535cbb35a6		2017-10-01 14:19:01	\N	2017-10-01 14:19:01	2017-10-01 14:19:10	18	approved	dffbf915cc7199dba01a13d2d50dbea4f8c8a8bfdd68bd92f42e2c535cbb35a6.png	image/png	42778	2017-10-01 14:19:00
10	\N	\N	glycine	\r\n  ChemDraw08161617062D\r\n\r\n  6  5  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.8250    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.8250    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\nM  END\r\n	templates/72196b29ca835329d1fded317c64a4d7b7952ee55ab6c6e14507c845bbc9064f.png	icons_small_8496c4499d9b2b6ec990d122709a36721953714b924b012a5c447e66fc19b41d20160826-27944-wbwa0n		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:30	6	approved	8496c4499d9b2b6ec990d122709a36721953714b924b012a5c447e66fc19b41d20160826-27944-wbwa0n.png	image/png	2444	2016-08-26 14:11:41
108	\N	\N	_16	\r\n  Ketcher 07261614192D\r\n\r\n 18 18  0  0  1  0  0  0  0  0999 V2000\r\n   -0.6627    0.6470    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4885    0.0182    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6627   -0.6023    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6296   -0.6023    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4885    0.0182    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6296    0.6470    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4885    0.5461    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4885   -0.6023    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4885    0.6123    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4885   -0.5461    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6296   -0.0480    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6296   -1.1749    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6627   -1.1749    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6627   -0.0811    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6296    1.1749    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6627    1.1749    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6710    0.2333    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6429    0.2615    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  1      \r\n  3  4  1  1      \r\n  5  4  1  1      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  2  7  1  0      \r\n  2  8  1  0      \r\n  5  9  1  0      \r\n  5 10  1  0      \r\n  4 11  1  0      \r\n  4 12  1  0      \r\n  3 13  1  0      \r\n  3 14  1  0      \r\n  6 15  1  0      \r\n  1 16  1  0      \r\n  1 17  1  0      \r\n  6 18  1  0      \r\nM  END\r\n	\N	icons_small_09056cb1221fc9c8174f04ecd05e9a307404b89e9ad2153a9fce20e96eda4e0c20160830-29185-1bpmrbk		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2016-11-30 09:46:35	7	approved	09056cb1221fc9c8174f04ecd05e9a307404b89e9ad2153a9fce20e96eda4e0c20160830-29185-1bpmrbk.png	image/png	9258	2016-08-30 06:51:28
109	\N	\N	_17	\r\n  Ketcher 07261614192D\r\n\r\n  6  6  0  0  1  0  0  0  0  0999 V2000\r\n   -0.3571    0.3353    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8021   -0.0018    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3571   -0.3353    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3393   -0.3353    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8021   -0.0018    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3393    0.3353    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  1      \r\n  3  4  1  1      \r\n  5  4  1  1      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\nM  END\r\n	\N	icons_small_d22ec3fa97d321921fef75946cb17c18ae652508b56b80ff208c6238c11594b420160830-29185-7h3coe		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2016-11-30 09:46:35	7	approved	d22ec3fa97d321921fef75946cb17c18ae652508b56b80ff208c6238c11594b420160830-29185-7h3coe.png	image/png	2322	2016-08-30 06:51:28
136	\N	\N	_10	\r\n  Ketcher 07261614192D\r\n\r\n  5  4  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7144   -0.8245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000   -0.4119    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7144   -0.8245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000    0.4133    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7144    0.8245    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  2  0      \r\n  4  5  1  0      \r\nM  END\r\n	\N	icons_small_34f0844382b5cc7a9e999cc1228a6251619c5df8aabe3cb9f87cc5cd1731e5d920160830-1161-1uywd39		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	34f0844382b5cc7a9e999cc1228a6251619c5df8aabe3cb9f87cc5cd1731e5d920160830-1161-1uywd39.png	image/png	4733	2016-08-30 08:35:18
112	\N	\N	_20	\r\n  Ketcher 07261614192D\r\n\r\n 15 15  0  0  1  0  0  0  0  0999 V2000\r\n   -0.8017   -0.3828    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2953   -0.5567    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2953    0.6762    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2953   -0.4864    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2953    0.6376    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8017   -0.9431    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7982   -0.9889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0009   -0.1000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8017    0.1037    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2953    0.1037    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2953    0.1037    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7982   -0.3828    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7982    0.1037    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0009    0.4532    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0009    0.9889    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n 12  1  1  1      \r\n 11  1  1  1      \r\n 10 12  1  1      \r\n 10  2  1  0      \r\n 10  3  1  0      \r\n 11  4  1  0      \r\n 11  5  1  0      \r\n  1  6  1  0      \r\n 12  7  1  0      \r\n 14  8  1  0      \r\n  1  9  1  0      \r\n 14 10  1  0      \r\n 11 14  1  0      \r\n 12 13  1  0      \r\n 14 15  1  0      \r\nM  END\r\n	\N	icons_small_fc22d421f101246bd6e072dcfb9ad3ac216b9fe7ca4fd9c7add3486e366649a920160830-29185-1w8qhd8		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2016-11-30 09:46:36	7	approved	fc22d421f101246bd6e072dcfb9ad3ac216b9fe7ca4fd9c7add3486e366649a920160830-29185-1w8qhd8.png	image/png	8978	2016-08-30 06:51:28
114	\N	\N	boat	\r\n  Ketcher 07261614192D\r\n\r\n 18 18  0  0  1  0  0  0  0  0999 V2000\r\n   -0.7690    0.3969    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6107    0.9469    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3416    0.3969    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7286   -0.9593    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0732   -0.1342    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9958   -0.5697    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4547   -0.9514    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4333    0.3935    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5310    0.9593    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7690    0.3935    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3416    0.3935    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0662   -0.0443    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1852   -0.6045    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5714   -0.4092    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7690   -0.0443    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2966    0.1779    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2649   -0.4114    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9958   -0.1690    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n 15 10  1  0      \r\n  1 14  1  1      \r\n  1 12  1  0      \r\n 15 12  1  0      \r\n  1  2  1  0      \r\n  1  3  1  0      \r\n 14  4  1  0      \r\n 14  5  1  0      \r\n 15  6  1  0      \r\n 17  7  1  0      \r\n 12  8  1  0      \r\n 10  9  1  0      \r\n 10 17  1  1      \r\n 10 11  1  0      \r\n 12 13  1  0      \r\n 17 14  1  1      \r\n 15 16  1  0      \r\n 17 18  1  0      \r\nM  END\r\n	\N	icons_small_a7dc21b136eed9ecdbd5818057d033e33434d8536e835099827d6cff1896a3be20160830-29185-3g67lx		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2017-10-01 13:02:39	7	approved	a7dc21b136eed9ecdbd5818057d033e33434d8536e835099827d6cff1896a3be20160830-29185-3g67lx.png	image/png	10207	2016-08-30 06:51:28
116	\N	\N	_24	\r\n  Ketcher 07261614192D\r\n\r\n 14 14  0  0  0  0  0  0  0  0999 V2000\r\n   -1.5609    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6062    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7946    0.7865    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7784   -0.7865    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5052    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5505    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7946    1.6110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5884    0.5650    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5609   -0.7833    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.3159    0.3727    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7784   -1.6110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5868   -0.6216    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.3159   -0.3775    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6062    0.8657    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  5  1  1  0      \r\n  6  2  1  0      \r\n  1  3  1  0      \r\n  2  4  1  0      \r\n  3  4  1  0      \r\n  5  6  2  0      \r\n  3  7  1  0      \r\n  3  8  1  0      \r\n  1  9  1  0      \r\n  1 10  1  0      \r\n  4 11  1  0      \r\n  4 12  1  0      \r\n  2 13  1  0      \r\n  2 14  1  0      \r\nM  END\r\n	\N	icons_small_23c409d870a936aec8554457fc657bd6896f8a4a3b2f709cf19e37e20ad60bb920160830-29185-18pej3g		2016-08-30 06:51:28	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	23c409d870a936aec8554457fc657bd6896f8a4a3b2f709cf19e37e20ad60bb920160830-29185-18pej3g.png	image/png	6657	2016-08-30 06:51:28
118	\N	\N	_26	\r\n  Ketcher 07261614192D\r\n\r\n 14 14  0  0  1  0  0  0  0  0999 V2000\r\n    0.5864    0.5706    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5846    0.5706    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1702    0.1429    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3416   -0.0410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3757   -0.3996    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1702    0.1429    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3416    0.4971    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7756   -0.3584    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3324   -0.8396    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9057   -0.3028    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7082    0.1429    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0509    0.8396    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0527    0.8396    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7082    0.1429    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  1      \r\n  4  5  1  1      \r\n  6  5  1  1      \r\n  1  6  2  0      \r\n  4  7  1  0      \r\n  4  8  1  0      \r\n  5  9  1  0      \r\n  5 10  1  0      \r\n  3 11  1  0      \r\n  2 12  1  0      \r\n  1 13  1  0      \r\n  6 14  1  0      \r\nM  END\r\n	\N	icons_small_6405c8816b3fea03843a05b4fc844195bd43081adb01ffc412722e9c7a5a2a4f20160830-29185-cg0zpv		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	6405c8816b3fea03843a05b4fc844195bd43081adb01ffc412722e9c7a5a2a4f20160830-29185-cg0zpv.png	image/png	7386	2016-08-30 06:51:29
137	\N	\N	_11	\r\n  Ketcher 07261614192D\r\n\r\n  7  6  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0721   -0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3578    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3564   -0.4118    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3578    0.8257    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3564    1.2368    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3564   -1.2368    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0721    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  2  0      \r\n  4  5  1  0      \r\n  3  6  1  0      \r\n  3  7  1  0      \r\nM  END\r\n	\N	icons_small_1fbcca9bbf93c3722f1f5cd647eb090dfd04fa818cfd4c6033fe3e6b2128e29c20160830-1161-1adom5d		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	1fbcca9bbf93c3722f1f5cd647eb090dfd04fa818cfd4c6033fe3e6b2128e29c20160830-1161-1adom5d.png	image/png	5281	2016-08-30 08:35:18
120	\N	\N	_28	\r\n  Ketcher 07261614192D\r\n\r\n 14 14  0  0  1  0  0  0  0  0999 V2000\r\n   -1.5788    0.0162    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5785    0.6932    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5788    0.8177    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4786   -0.1099    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4816   -1.2766    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.3755    0.2295    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1619    1.2766    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.3755    1.0310    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9324    0.9453    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3490    0.3620    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3490   -0.4622    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4816   -0.4525    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6545   -0.1099    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3057   -0.4525    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  1 12  1  1      \r\n  2 10  1  0      \r\n 10  3  1  0      \r\n 13  3  2  0      \r\n 13  4  1  0      \r\n 12  5  1  0      \r\n  1  6  1  0      \r\n  2  7  1  0      \r\n  3  8  1  0      \r\n 10  9  1  0      \r\n 10 11  1  0      \r\n 13 12  1  1      \r\n 12 14  1  0      \r\nM  END\r\n	\N	icons_small_36569f3719e6e48ce2b643973fc97c7a6ae39f64964b46b7c790ccd3754f0d3e20160830-29185-mdu41s		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	36569f3719e6e48ce2b643973fc97c7a6ae39f64964b46b7c790ccd3754f0d3e20160830-29185-mdu41s.png	image/png	7376	2016-08-30 06:51:29
121	\N	\N	_29	\r\n  Ketcher 07261614192D\r\n\r\n 21 21  0  0  1  0  0  0  0  0999 V2000\r\n   -0.7541    0.6223    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7353    0.0550    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8177   -0.6223    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3231    1.1736    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8177   -1.4468    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.5322   -0.2101    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7541   -1.3352    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5785   -0.5108    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.5322   -0.1584    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7353    0.8794    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7541    1.4468    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5510    0.4090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1200    0.1358    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3231    0.3492    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9416    0.4672    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3403    0.6062    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0558    0.0550    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0558   -0.9376    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7541   -0.5108    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3403   -0.2182    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2433   -0.8018    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2 19  1  1      \r\n  1 17  1  0      \r\n  3 20  1  1      \r\n 14  3  1  0      \r\n 14  4  1  0      \r\n  3  5  1  0      \r\n  3  6  1  0      \r\n 19  7  1  0      \r\n 19  8  1  0      \r\n  2  9  1  0      \r\n  2 10  1  0      \r\n  1 11  1  0      \r\n  1 12  1  0      \r\n 14 13  1  0      \r\n 17 14  1  0      \r\n 17 15  1  0      \r\n 20 16  1  0      \r\n 17 18  1  0      \r\n 19 20  1  1      \r\n 20 21  1  0      \r\nM  END\r\n	\N	icons_small_dff982036fe70827451dd4583b546271d5322c9a2e76551d7c842180a3f2741220160830-29185-1bz04so		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	dff982036fe70827451dd4583b546271d5322c9a2e76551d7c842180a3f2741220160830-29185-1bz04so.png	image/png	9340	2016-08-30 06:51:29
122	\N	\N	_30	\r\n  Ketcher 07261614192D\r\n\r\n 21 21  0  0  1  0  0  0  0  0999 V2000\r\n   -0.3737    0.3584    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0885    0.1652    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5659   -0.8958    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0864   -0.2180    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5551   -0.1040    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0885    0.7036    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3737    0.8968    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8404    0.0892    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9396   -0.6762    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4128   -0.8968    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0885    0.8937    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9396   -0.1378    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0251   -0.2455    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0412   -0.1378    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0412   -0.6762    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5659   -0.3574    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4128   -0.3584    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5078    0.1314    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0885    0.3553    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5551    0.0860    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4601    0.0016    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2 16  1  1      \r\n  1 14  1  0      \r\n 12 19  1  0      \r\n 16  3  1  0      \r\n 16  4  1  0      \r\n  2  5  1  0      \r\n  2  6  1  0      \r\n  1  7  1  0      \r\n  1  8  1  0      \r\n 12  9  1  0      \r\n 17 10  1  0      \r\n 14 12  1  0      \r\n 19 11  1  0      \r\n 19 17  1  1      \r\n 17 13  1  0      \r\n 14 15  1  0      \r\n 16 17  1  1      \r\n 14 18  1  0      \r\n 19 20  1  0      \r\n 12 21  1  0      \r\nM  END\r\n	\N	icons_small_f1701fe583b40ccf294806e53ca62696d88dae37ef77c79e561bf8d58bd446c420160830-29185-1cysf1r		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	f1701fe583b40ccf294806e53ca62696d88dae37ef77c79e561bf8d58bd446c420160830-29185-1cysf1r.png	image/png	9923	2016-08-30 06:51:29
123	\N	\N	_31	\r\n  Ketcher 07261614192D\r\n\r\n 15 15  0  0  1  0  0  0  0  0999 V2000\r\n    1.7971   -0.0612    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6666   -0.7463    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3305    0.7463    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2767   -0.1710    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6233    0.2713    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0265   -0.7463    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7971   -0.0317    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9822    0.6101    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3552   -0.1288    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0174    0.0549    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5600   -0.4771    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7426    0.0549    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1648   -0.1288    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2000   -0.4771    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3305    0.2079    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n 15  1  1  0      \r\n 14  2  1  0      \r\n  4  5  2  0      \r\n  4 11  1  1      \r\n  5 10  1  0      \r\n 11  6  1  0      \r\n  4  7  1  0      \r\n  5  8  1  0      \r\n 10  9  1  0      \r\n 12 10  2  0      \r\n 14 11  2  0      \r\n 15  3  1  0      \r\n 12 15  1  0      \r\n 12 13  1  0      \r\n 15 14  1  1      \r\nM  END\r\n	\N	icons_small_daa95caa729494c5966aeb945f19b2e2419d3e3de49a783b0ddb8f96d2ee7d0e20160830-29185-4lsqlz		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	daa95caa729494c5966aeb945f19b2e2419d3e3de49a783b0ddb8f96d2ee7d0e20160830-29185-4lsqlz.png	image/png	6685	2016-08-30 06:51:29
124	\N	\N	_32	\r\n  Ketcher 07261614192D\r\n\r\n 24 24  0  0  1  0  0  0  0  0999 V2000\r\n   -0.9567    0.6504    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.9375    0.0832    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9375   -0.1737    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1199    1.2015    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9375   -0.9979    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.7342    0.0396    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9567   -1.3065    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7808   -0.4824    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.7342   -0.1301    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.9375    0.9074    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9567    1.4746    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7533    0.4371    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9165    0.1640    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1199    0.3773    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7385    0.4953    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1374    0.6343    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1471    0.0832    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1471   -0.9090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9567   -0.4824    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1374   -0.1899    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4460   -0.7732    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0811   -0.6504    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0811   -1.4746    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1153   -0.3919    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2 19  1  1      \r\n  1 17  1  0      \r\n 14  3  1  0      \r\n 14  4  1  0      \r\n  3  5  1  0      \r\n  3  6  1  0      \r\n 19  7  1  0      \r\n 19  8  1  0      \r\n  2  9  1  0      \r\n  2 10  1  0      \r\n  1 11  1  0      \r\n  1 12  1  0      \r\n 14 13  1  0      \r\n 17 14  1  0      \r\n 17 15  1  0      \r\n 20 16  1  0      \r\n 17 18  1  0      \r\n 19 20  1  1      \r\n 20 21  1  0      \r\n 20 22  1  1      \r\n  3 22  1  1      \r\n 22 23  1  0      \r\n 22 24  1  0      \r\nM  END\r\n	\N	icons_small_e74c488478f0ff70baa57f9a872d50462eb3beee10ae8ce04c7c1ece0d80a4f020160830-29185-1x9qq1a		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	e74c488478f0ff70baa57f9a872d50462eb3beee10ae8ce04c7c1ece0d80a4f020160830-29185-1x9qq1a.png	image/png	10239	2016-08-30 06:51:29
140	\N	\N	_14	\r\n  Ketcher 07261614192D\r\n\r\n  4  3  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7145   -0.6767    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.2643    0.0000 S   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7145   -0.6767    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    0.6767    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  2  0      \r\nM  END\r\n	\N	icons_small_5dce8df91b0fa93b9037742169541c0d979f19f9cf95dedb90119eea41966cee20160830-1161-68a9ad		2016-08-30 08:35:18	\N	2016-08-30 08:35:19	2016-11-30 09:46:37	17	approved	5dce8df91b0fa93b9037742169541c0d979f19f9cf95dedb90119eea41966cee20160830-1161-68a9ad.png	image/png	4101	2016-08-30 08:35:18
127	\N	\N	_1	\n  Ketcher 07261614192D\r\n\r\n  3  2  0  0  0  0  0  0  0  0999 V2000\r\n   -0.8250    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8250    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  3  0      \r\nM  END\r\n	\N	icons_small_209602665b97ef9ec64a451d4d8168a717e17948b3da19f1ccedd5f7035f486b20160830-1161-uxb5w7		2016-08-30 08:35:17	\N	2016-08-30 08:35:17	2016-11-30 09:46:36	17	approved	209602665b97ef9ec64a451d4d8168a717e17948b3da19f1ccedd5f7035f486b20160830-1161-uxb5w7.png	image/png	2523	2016-08-30 08:35:17
128	\N	\N	_2	\r\n  Ketcher 07261614192D\r\n\r\n  4  3  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0722   -0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3574    0.4120    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3574   -0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0722   -0.4120    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  3  0      \r\nM  END\r\n	\N	icons_small_e2e7f354fa2c3ae019d3495536293c1c5d3738f18844d89fc4cefb0174c3c09320160830-1161-v428ot		2016-08-30 08:35:17	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	e2e7f354fa2c3ae019d3495536293c1c5d3738f18844d89fc4cefb0174c3c09320160830-1161-v428ot.png	image/png	3310	2016-08-30 08:35:17
129	\N	\N	_3	\r\n  Ketcher 07261614192D\r\n\r\n  6  5  0  0  1  0  0  0  0  0999 V2000\r\n   -1.4693    0.3564    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7550    0.7689    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6720   -0.0547    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0859   -0.7689    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4693   -0.2675    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0423    0.3564    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  2  6  2  0      \r\n  3  6  2  0      \r\n  1  2  1  0      \r\n  3  4  1  1      \r\n  3  5  1  6      \r\nM  STY  1   1 SUP\r\nM  SLB  1   1   1\r\nM  SAL   1  1   6\r\nM  SBL   1  2   1   2\r\nM  SMT   1 �\r\nM  SBV   1   1   -0.7128    0.4125\r\nM  SBV   1   2    0.7142   -0.4110\r\nM  END\r\n	\N	icons_small_e8dcaf0cd5bb72e0ac3c3ed34d76800facb65d3a7faea0b3057eaf3aee6c56bd20160830-1161-1dwd38i		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	e8dcaf0cd5bb72e0ac3c3ed34d76800facb65d3a7faea0b3057eaf3aee6c56bd20160830-1161-1dwd38i.png	image/png	4627	2016-08-30 08:35:18
130	\N	\N	_4	\r\n  Ketcher 07261614192D\r\n\r\n  4  3  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0714   -0.2054    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3576    0.2068    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3562   -0.2068    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0714    0.2068    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\nM  END\r\n	\N	icons_small_c259a9e391e1aefd48e4f5795d95d2c9dad00d8035e4973844a8a531207635c320160830-1161-nl9o2a		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	c259a9e391e1aefd48e4f5795d95d2c9dad00d8035e4973844a8a531207635c320160830-1161-nl9o2a.png	image/png	3588	2016-08-30 08:35:18
131	\N	\N	_5	\r\n  Ketcher 07261614192D\r\n\r\n  3  2  0  0  0  0  0  0  0  0999 V2000\r\n   -0.8250    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000    0.0000    0.0000 N   0  3  0  0  0  0  0  0  0  0  0  0\r\n    0.8250    0.0000    0.0000 N   0  5  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  2  0      \r\nM  CHG  2   2   1   3  -1\r\nM  END\r\n	\N	icons_small_94161f3d49016def545171088379e39dc988ed0d544ed4d0f51aad3eaf0792eb20160830-1161-17l8659		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	94161f3d49016def545171088379e39dc988ed0d544ed4d0f51aad3eaf0792eb20160830-1161-17l8659.png	image/png	2432	2016-08-30 08:35:18
132	\N	\N	_6	\r\n  Ketcher 07261614192D\r\n\r\n  4  3  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0727    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3576    0.4121    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3576    0.0007    0.0000 N   0  3  0  0  0  0  0  0  0  0  0  0\r\n    1.0727   -0.4121    0.0000 N   0  5  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  2  0      \r\nM  CHG  2   3   1   4  -1\r\nM  END\r\n	\N	icons_small_a0a4da64b4967974059258dbcebc001c2afc9eb3e8c166edfc37f99c2cfd076e20160830-1161-ff56w1		2016-08-30 08:35:18	\N	2016-08-30 08:35:18	2016-11-30 09:46:37	17	approved	a0a4da64b4967974059258dbcebc001c2afc9eb3e8c166edfc37f99c2cfd076e20160830-1161-ff56w1.png	image/png	3529	2016-08-30 08:35:18
146	\N	\N	threonine	Threonin.mol\r\n  ChemDraw10011714012D\r\n\r\n  8  7  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.4124    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.4124    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -0.4126    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  4  8  1  0      \r\nM  END\r\n	\N	icons_small_2bedd3e7892df7afb05791075118a215ff92138eecacb37de404690639d524e0		2017-10-01 11:58:20	\N	2017-10-01 11:58:22	2017-10-01 12:12:27	6	approved	2bedd3e7892df7afb05791075118a215ff92138eecacb37de404690639d524e0.png	image/png	26908	2017-10-01 12:02:10
147	\N	\N	leucine	\r\n  Ketcher 10011714102D 1   1.00000     0.00000     0\r\n\r\n  9  8  0     0  0            999 V2000\r\n   -0.6750   -2.1500    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3251   -2.1500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3250   -2.1500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3251   -3.1501    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.3250   -2.1500    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3250   -1.1500    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3251   -4.1500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3250   -4.1500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3251   -5.1500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  2  4  1  0     0  0\r\n  3  5  1  0     0  0\r\n  3  6  2  0     0  0\r\n  4  7  1  0     0  0\r\n  7  8  1  0     0  0\r\n  7  9  1  0     0  0\r\nM  END\r\n$$$$\r\n\r\n	\N	icons_small_920495d7aa24df70dc89246b2adae0d8a6833f82ba5dbe55b2fc724a1be55046		2017-10-01 12:05:25	\N	2017-10-01 12:05:25	2017-10-01 12:11:56	6	approved	920495d7aa24df70dc89246b2adae0d8a6833f82ba5dbe55b2fc724a1be55046.png	image/png	27030	2017-10-01 12:10:51
148	\N	\N	isoleucine	Isoleucin.mol\r\n  ChemDraw10011714072D\r\n\r\n  9  8  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.8249    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.0001    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.8249    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.6499    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -0.0001    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.6499    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  4  8  1  0      \r\n  8  9  1  0      \r\nM  END\r\n	\N	icons_small_322ca01cd9bd171d878d85878b8deac6f1257720688bf47cbc10c577f843e448		2017-10-01 12:08:11	\N	2017-10-01 12:08:12	2017-10-01 12:12:46	6	approved	322ca01cd9bd171d878d85878b8deac6f1257720688bf47cbc10c577f843e448.png	image/png	25315	2017-10-01 12:08:12
149	\N	\N	serine	serine.mol\r\n  ChemDraw10011714212D\r\n\r\n  7  6  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    0.4124    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4126    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    0.4124    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\nM  END\r\n	\N	icons_small_db158ab16b1dd8b52ce17f66745d19ef110733f4a9b0498d6718511584f0c380		2017-10-01 12:22:16	\N	2017-10-01 12:22:18	2017-10-01 12:22:18	6	approved	db158ab16b1dd8b52ce17f66745d19ef110733f4a9b0498d6718511584f0c380.png	image/png	21841	2017-10-01 12:22:18
150	\N	\N	tymine (DNA)	thymine.mol\r\n  ChemDraw10011715172D\r\n\r\n  9  9  0  0  0  0  0  0  0  0999 V2000\r\n    0.7145    0.0299    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7145   -0.7946    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0007   -1.2083    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7146   -0.7946    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7146    0.0299    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0007    0.4421    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0007    1.2083    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4312   -1.2083    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4312    0.4421    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  6  7  2  0      \r\n  2  8  2  0      \r\n  5  9  1  0      \r\nM  END\r\n	\N	icons_small_ceeccc2d64b9fa25ccfa2966e62ab9f136be279e782ff29973b95803794cc397		2017-10-01 13:24:21	\N	2017-10-01 13:24:22	2017-10-01 13:24:35	3	approved	ceeccc2d64b9fa25ccfa2966e62ab9f136be279e782ff29973b95803794cc397.png	image/png	40306	2017-10-01 13:24:21
151	\N	\N	thymidine (DNA) - nucleoside	thymine-nucleoside.mol\r\n  ChemDraw10011715202D\r\n\r\n 20 21  0  0  1  0  0  0  0  0999 V2000\r\n   -1.0437   -2.1339    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3439   -2.1339    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3514   -1.2360    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4737   -1.6499    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3439   -2.6790    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0437   -2.6790    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7652   -2.3583    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4737   -0.9882    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4737   -2.3583    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.1892   -0.5743    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7652   -1.6499    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0422    1.4999    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0422    0.6749    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7564    0.2609    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4721    0.6749    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4721    1.4999    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7564    1.9123    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7564    2.6790    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1892    0.2609    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6734    1.9123    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  1      \r\n  3  4  1  0      \r\n  4  1  1  1      \r\n  2  5  1  0      \r\n  1  6  1  0      \r\n  4  8  1  0      \r\n  4  9  1  0      \r\n  8 10  1  0      \r\n 12 13  2  0      \r\n 13 14  1  0      \r\n 14 15  1  0      \r\n 15 16  1  0      \r\n 16 17  1  0      \r\n 12 17  1  0      \r\n 17 18  2  0      \r\n 11 14  1  0      \r\n 15 19  2  0      \r\n 12 20  1  0      \r\n 11  2  1  1      \r\n  3 11  1  0      \r\n  7 11  1  0      \r\nM  END\r\n	\N	icons_small_e1c74ef2cf3d4a056857d3b75e8981619a28404c9e8a3c9761e5674551b7de57		2017-10-01 13:25:49	\N	2017-10-01 13:25:49	2017-10-01 13:27:07	3	approved	e1c74ef2cf3d4a056857d3b75e8981619a28404c9e8a3c9761e5674551b7de57.png	image/png	49361	2017-10-01 13:25:49
152	\N	\N	tymine (DNA) nucleotide 1	thymine-nucleotide 1.mol\r\n  ChemDraw10011715202D\r\n\r\n 24 25  0  0  1  0  0  0  0  0999 V2000\r\n    0.9284    1.3650    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9284    0.5400    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.3583    0.5400    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.3583    1.3650    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6426    1.7775    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6426    2.5442    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.0754    0.1261    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2127    1.7775    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6426    0.1261    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1663   -1.9991    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2214   -1.9991    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6426   -1.5151    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5640   -1.0720    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5903   -1.5151    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2214   -2.5442    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1663   -2.5442    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6426   -2.2235    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5903   -0.8534    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5903   -2.2235    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4226   -0.8534    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.2491   -0.8534    0.0000 P   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -3.0754   -0.8534    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n   -2.2491   -1.6798    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0\r\n   -2.2491   -0.0327    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  1  5  1  0      \r\n  5  6  2  0      \r\n  3  7  2  0      \r\n  1  8  1  0      \r\n 10 11  1  1      \r\n 12 11  1  1      \r\n 12 13  1  0      \r\n 13 14  1  0      \r\n 14 10  1  1      \r\n 11 15  1  0      \r\n 10 16  1  0      \r\n 12 17  1  0      \r\n 14 18  1  0      \r\n 14 19  1  0      \r\n  9 12  1  0      \r\n 18 20  1  0      \r\n 20 21  1  0      \r\n 21 22  1  0      \r\n 21 23  1  0      \r\n 21 24  2  0      \r\n  9  2  1  0      \r\n  9  3  1  0      \r\nM  CHG  2  22  -1  23  -1\r\nM  END\r\n	\N	icons_small_b77a85b9187540e28fd40417d836ec6d971762ed6a0bb17abdf2bedb78b5dd97		2017-10-01 13:26:20	\N	2017-10-01 13:26:21	2017-10-01 13:26:57	3	approved	b77a85b9187540e28fd40417d836ec6d971762ed6a0bb17abdf2bedb78b5dd97.png	image/png	48968	2017-10-01 13:26:21
2	\N	\N	quinoxalinone	\r\n  Ketcher 10011714332D 1   1.00000     0.00000     0\r\n\r\n 12 13  0     0  0            999 V2000\r\n    3.6000   -3.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    4.4660   -4.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    4.4660   -5.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.6000   -5.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.7340   -5.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.7340   -4.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.3321   -3.6750    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.1981   -4.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.1981   -5.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.3320   -5.6750    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.0641   -5.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.0641   -3.6750    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  2  0     0  0\r\n  3  4  1  0     0  0\r\n  4  5  2  0     0  0\r\n  5  6  1  0     0  0\r\n  6  1  2  0     0  0\r\n  2  7  1  0     0  0\r\n  7  8  1  0     0  0\r\n  8  9  1  0     0  0\r\n  9 10  2  0     0  0\r\n 10  3  1  0     0  0\r\n  9 11  1  0     0  0\r\n  8 12  2  0     0  0\r\nM  END\r\n$$$$\r\n\r\n	templates/032d77ddffe149ca9f0fe6ac4c92724267b0375ba26af37aed03a238e6a85b8c.png	icons_small_c90922013eea2b61a1e73f1f1e4f2d74560a227b591c7b7f4b59890ebe25038e		2016-07-29 12:28:23	\N	2016-07-29 12:28:23	2017-10-01 12:33:41	4	pending	c90922013eea2b61a1e73f1f1e4f2d74560a227b591c7b7f4b59890ebe25038e.png	image/png	27900	2017-10-01 12:33:40
8	\N	\N	glutamic acid	\r\n  ChemDraw08161617062D\r\n\r\n 10  9  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    1.2374    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2374    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    1.2374    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.0624    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.2375    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.0624    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124   -1.2375    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  8 10  2  0      \r\nM  END\r\n	templates/7f7daa5d8bf27ed2c0f995c2e872f8a1a100f2ea622b189b397014c5e5d0c7ca.png	icons_small_153bdcd54c027c3ddddf40cff59ec03c9dac8b7348d3faad617a444bcf79def020160826-27944-1q7x774		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:29	6	approved	153bdcd54c027c3ddddf40cff59ec03c9dac8b7348d3faad617a444bcf79def020160826-27944-1q7x774.png	image/png	3000	2016-08-26 14:11:41
159	\N	\N	Benzyl alcohol resin	\r\n  Ketcher 10011716222D 1   1.00000     0.00000     0\r\n\r\n  9  9  0     0  0            999 V2000\r\n    4.0170   -5.5000    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    4.8830   -5.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    4.8830   -4.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.7491   -3.5000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.6151   -4.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.6151   -5.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.7490   -5.5000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.4811   -3.5000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.3471   -4.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  3  4  2  0     0  0\r\n  4  5  1  0     0  0\r\n  5  6  2  0     0  0\r\n  6  7  1  0     0  0\r\n  7  2  2  0     0  0\r\n  5  8  1  0     0  0\r\n  8  9  1  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_428854a0b252c6cd8da5377df35fa97d90e1dcd5bb06e8c17606643d47ed3a3a		2017-10-01 14:22:58	\N	2017-10-01 14:22:58	2017-10-01 14:22:58	18	approved	428854a0b252c6cd8da5377df35fa97d90e1dcd5bb06e8c17606643d47ed3a3a.png	image/png	33893	2017-10-01 14:22:57
160	\N	\N	Aminotrityl resin	\r\n  Ketcher 10011716252D 1   1.00000     0.00000     0\r\n\r\n 21 23  0     0  0            999 V2000\r\n    6.1170   -7.6750    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.0330   -7.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.5330   -6.8090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.5330   -6.8090    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.0330   -7.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.5330   -8.5410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.5330   -8.5410    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.0330   -7.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.0330   -6.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.0330   -8.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   11.0330   -7.6750    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.1670   -6.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.1670   -5.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.0330   -4.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.8991   -5.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.8991   -6.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.8991   -9.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.8991  -10.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.0330  -10.6750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.1670  -10.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.1670   -9.1750    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  3  4  2  0     0  0\r\n  4  5  1  0     0  0\r\n  5  6  2  0     0  0\r\n  6  7  1  0     0  0\r\n  7  2  2  0     0  0\r\n  5  8  1  0     0  0\r\n  8  9  1  0     0  0\r\n  8 10  1  0     0  0\r\n  8 11  1  0     0  0\r\n  9 12  1  0     0  0\r\n 12 13  2  0     0  0\r\n 13 14  1  0     0  0\r\n 14 15  2  0     0  0\r\n 15 16  1  0     0  0\r\n 16  9  2  0     0  0\r\n 10 17  1  0     0  0\r\n 17 18  2  0     0  0\r\n 18 19  1  0     0  0\r\n 19 20  2  0     0  0\r\n 20 21  1  0     0  0\r\n 21 10  2  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_24af4af690275f2b4045eb89a3b92e304f962579748a9efb5754069868629e95		2017-10-01 14:25:18	\N	2017-10-01 14:25:18	2017-10-01 14:25:18	18	approved	24af4af690275f2b4045eb89a3b92e304f962579748a9efb5754069868629e95.png	image/png	42713	2017-10-01 14:25:17
161	\N	\N	DHP resin	\r\n  Ketcher 10011716282D 1   1.00000     0.00000     0\r\n\r\n  9  9  0     0  0            999 V2000\r\n    4.7420   -6.4250    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    5.9580   -6.4500    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.4401   -7.3261    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.4399   -7.3467    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.9399   -6.4807    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.9399   -6.4807    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.4399   -7.3467    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.9399   -8.2127    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.9399   -8.2127    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  3  4  1  0     0  0\r\n  4  5  1  0     0  0\r\n  5  6  1  0     0  0\r\n  6  7  2  0     0  0\r\n  7  8  1  0     0  0\r\n  8  9  1  0     0  0\r\n  9  4  1  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_ed4820da21d42006dc8251094c6ee0f1e088c28e5f40977e62e51ca4de9b266f		2017-10-01 14:28:18	\N	2017-10-01 14:28:18	2017-10-01 14:28:18	18	approved	ed4820da21d42006dc8251094c6ee0f1e088c28e5f40977e62e51ca4de9b266f.png	image/png	37569	2017-10-01 14:28:18
14	\N	\N	phenylalanine	\r\n  ChemDraw08161617062D\r\n\r\n 12 12  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    1.2396    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    1.2396    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.2396    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.4146    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    1.2396    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.0646    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -0.4103    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1268   -0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1268   -1.6514    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.0646    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3005   -1.6514    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3005   -0.8249    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n 10 11  1  0      \r\n 11 12  2  0      \r\n  7 12  1  0      \r\nM  END\r\n	templates/bf697cef807874e7b4b6572e5305bf116e50f46b5c3c2551e3c5adf262898244.png	icons_small_a4dd49c631117803e7ecc86b2f41858c3890300fe16e3c2bf4b25d12d9b6a8fd20160826-27944-195jjfc		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2017-10-01 11:57:57	6	approved	a4dd49c631117803e7ecc86b2f41858c3890300fe16e3c2bf4b25d12d9b6a8fd20160826-27944-195jjfc.png	image/png	3678	2016-08-26 14:11:42
17	\N	\N	tryptophane	\r\n  ChemDraw08161617062D\r\n\r\n 15 16  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4202    1.3533    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5951    1.3533    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2299    1.3533    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5951    0.5282    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0550    1.3533    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2299    2.1784    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5951   -0.2968    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2617   -0.7843    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0055   -1.5686    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1819   -1.5686    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0698   -0.7843    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3696   -2.1784    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1714   -2.0051    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4202   -1.2238    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8658   -0.6170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  2  0      \r\n  7 11  1  0      \r\n 10 12  1  0      \r\n 12 13  2  0      \r\n 13 14  1  0      \r\n 14 15  2  0      \r\n 11 15  1  0      \r\nM  END\r\n	templates/67a32af82fd40dad97dcecb48d644b78d0dd9121fa6601b529dccc3f90cbf238.png	icons_small_d41cf826306953c1b784b246e23a07108894eb7d383c665d77303e070be4656620160826-27944-10ckshp		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2017-10-01 12:13:26	6	approved	d41cf826306953c1b784b246e23a07108894eb7d383c665d77303e070be4656620160826-27944-10ckshp.png	image/png	5543	2016-08-26 14:11:42
18	\N	\N	tyrosine	\r\n  ChemDraw08161617062D\r\n\r\n 13 13  0  0  0  0  0  0  0  0999 V2000\r\n   -1.2374    1.6520    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    1.6520    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    1.6520    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.8270    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2374    1.6520    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4124    2.4770    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124    0.0022    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1268   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1268   -1.2390    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -1.6522    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3005   -1.2390    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3005   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4124   -2.4770    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  3  5  1  0      \r\n  3  6  2  0      \r\n  4  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n 10 11  1  0      \r\n 11 12  2  0      \r\n  7 12  1  0      \r\n 10 13  1  0      \r\nM  END\r\n	templates/64b79f5eccaab6a6f6fd9dfc437f7de2170dcc019398e6af0346b487566302a4.png	icons_small_9faeb1c1f0e96486741a56f8177c48385ba0a821ab87a6ae0700f738a0efd2ae20160826-27944-9obkdq		2016-08-16 15:06:47	\N	2016-08-16 15:06:47	2016-11-30 09:46:30	6	approved	9faeb1c1f0e96486741a56f8177c48385ba0a821ab87a6ae0700f738a0efd2ae20160826-27944-9obkdq.png	image/png	3658	2016-08-26 14:11:43
24	\N	\N	biphenyl	\r\n  Ketcher 07261614192D\r\n\r\n 12 13  0  0  0  0  0  0  0  0999 V2000\r\n   -1.7868   -0.2058    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7868   -1.0305    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0727   -1.4436    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3571   -1.0305    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3571   -0.2058    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0727    0.2073    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3556    0.2073    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0727   -0.2029    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7868    0.2073    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7868    1.0334    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0727    1.4436    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3556    1.0334    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  1  6  1  0      \r\n  5  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n 10 11  1  0      \r\n 11 12  2  0      \r\n  7 12  1  0      \r\nM  END\r\n	templates/12b8ea27cb51c145fbc80f5dab713a84c82e11bfe7add19c2b3b41fff4cc308e.png	icons_small_63e225184ec326089e3ae5ecf2b055a84d82323c2169a1ca1c4362960b64ee5420160826-27944-u1w6nq		2016-08-16 15:24:46	\N	2016-08-16 15:24:46	2016-11-30 09:46:30	1	approved	63e225184ec326089e3ae5ecf2b055a84d82323c2169a1ca1c4362960b64ee5420160826-27944-u1w6nq.png	image/png	3624	2016-08-26 14:11:41
44	\N	\N	_8	\r\n  Ketcher 07261614192D\r\n\r\n  7  8  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0469    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0469   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2219   -0.4132    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2219    0.4118    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5624   -0.6679    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0469   -0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5624    0.6679    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  1  4  1  0      \r\n  3  5  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  4  7  1  0      \r\nM  END\r\n	templates/0c3bfa607f42c50407d8099637bd6b9a5fc52a4056b8c0c9b2cf4690f67a6387.png	icons_small_24610b97f7d0de7195d304ddeafa3bbdbac2cc082f4becfb120c04c046e9c5c520160826-27944-1ubeqnj		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	24610b97f7d0de7195d304ddeafa3bbdbac2cc082f4becfb120c04c046e9c5c520160826-27944-1ubeqnj.png	image/png	2840	2016-08-26 14:11:40
25	\N	\N	acenaphthylene	\r\n  Ketcher 07261614192D\r\n\r\n 12 14  0  0  0  0  0  0  0  0999 V2000\r\n   -0.0007   -0.0015    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0007   -0.8265    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7135   -1.2375    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4292   -0.8265    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4292   -0.0015    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7135    0.4140    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7150    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4292   -0.0015    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4292   -0.8265    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7150   -1.2360    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7150    1.2375    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7150    1.2375    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  1  6  1  0      \r\n  1  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n  2 10  1  0      \r\n  6 11  1  0      \r\n  7 12  1  0      \r\n 11 12  2  0      \r\nM  END\r\n	templates/f3c662b91edc83846165554fa855c22941089535f98ad63ee2437b5fff34230e.png	icons_small_2bde19a92fb6c90bdc54d6ffd87f157f01a55e62dfa506526a3df7a78c72aefa20160826-27944-yz2nz1		2016-08-16 15:24:46	\N	2016-08-16 15:24:46	2016-11-30 09:46:30	1	approved	2bde19a92fb6c90bdc54d6ffd87f157f01a55e62dfa506526a3df7a78c72aefa20160826-27944-yz2nz1.png	image/png	3809	2016-08-26 14:11:40
26	\N	\N	anthracene	\r\n  Ketcher 07261614192D\r\n\r\n 14 16  0  0  0  0  0  0  0  0999 V2000\r\n   -2.1450    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.1450   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4310   -0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7155   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7155    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4310    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0015   -0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7155   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7155    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0015    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4295   -0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1450   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1450    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4295    0.8257    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0      \r\n  2  3  1  0      \r\n  3  4  2  0      \r\n  4  5  1  0      \r\n  5  6  2  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n  5 10  1  0      \r\n  8 11  1  0      \r\n 11 12  2  0      \r\n 12 13  1  0      \r\n 13 14  2  0      \r\n  9 14  1  0      \r\nM  END\r\n	templates/1fef99f235650dfe9af2cf2b4302b3cf8a9a649f25aca525dee27f6f157eab5b.png	icons_small_ab6a5f8a5d20a5d04677d128b4a79455db9820f9ebc20df0eec9139c35fb784a20160826-27944-1gvnn4m		2016-08-16 15:24:46	\N	2016-08-16 15:24:47	2016-11-30 09:46:30	1	approved	ab6a5f8a5d20a5d04677d128b4a79455db9820f9ebc20df0eec9139c35fb784a20160826-27944-1gvnn4m.png	image/png	3727	2016-08-26 14:11:40
33	\N	\N	azulene	\r\n  Ketcher 07261614192D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n   -1.3856    0.2215    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3856   -0.6032    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7416   -1.1190    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0627   -0.9369    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4211   -0.1952    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0627    0.5478    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7416    0.7329    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2385   -0.0830    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3856    0.7285    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6586    1.1190    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  1  7  2  0      \r\n  5  8  1  0      \r\n  8  9  2  0      \r\n  9 10  1  0      \r\n  6 10  2  0      \r\nM  END\r\n	templates/aa557619ef7d731f33a1be14d84072c900d7e0522e40520b1ebc3d125526e983.png	icons_small_8dbbd55285eeb35f5c168e258f961c2aba9dfbef02154c395c015399361baec420160826-27944-pf9v3a		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	8dbbd55285eeb35f5c168e258f961c2aba9dfbef02154c395c015399361baec420160826-27944-pf9v3a.png	image/png	5316	2016-08-26 14:11:41
36	\N	\N	indene	\r\n  Ketcher 07261614192D\r\n\r\n  9 10  0  0  0  0  0  0  0  0999 V2000\r\n   -1.3494    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3494   -0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6350   -0.8256    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0807   -0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0807    0.4124    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6350    0.8256    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8649   -0.6670    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3494    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8649    0.6685    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  6  2  0      \r\n  4  7  2  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  5  9  2  0      \r\nM  END\r\n	templates/30ffe62b9a660daf8ebb9bd03313a5252b1c430f2f7e674a55e731884c987630.png	icons_small_f7bfeca1d18e7f426de5032ab6ae77455b5a296debddb06775d833817f8d00f320160826-27944-29k0eo		2016-08-16 15:24:47	\N	2016-08-16 15:24:47	2016-11-30 09:46:31	1	approved	f7bfeca1d18e7f426de5032ab6ae77455b5a296debddb06775d833817f8d00f320160826-27944-29k0eo.png	image/png	4287	2016-08-26 14:11:41
41	\N	\N	_5	\r\n  Ketcher 07261614192D\r\n\r\n  7  8  0  0  0  0  0  0  0  0999 V2000\r\n   -1.0036   -0.8208    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2068   -0.6067    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5899   -0.8208    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0036   -0.1071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5899   -0.1071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2068    0.1071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2054    0.8208    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  1  5  1  0      \r\n  5  6  1  0      \r\n  4  6  1  0      \r\n  6  7  1  0      \r\n  2  7  1  0      \r\nM  END\r\n	templates/403c208023975f81c428e9c6782a6a7a76603c2e2a08b14674457f0ef4aa5809.png	icons_small_788c93a2d273a3ef698644a960785308b6164239c1fa209c805e2613d1762ebb20160826-27944-1ljpjqa		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:31	2	approved	788c93a2d273a3ef698644a960785308b6164239c1fa209c805e2613d1762ebb20160826-27944-1ljpjqa.png	image/png	3958	2016-08-26 14:11:39
46	\N	\N	_10	\r\n  Ketcher 07261614192D\r\n\r\n  7  8  0  0  0  0  0  0  0  0999 V2000\r\n    1.0569   -0.7464    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5499   -0.0141    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5992   -0.5549    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0569    0.1000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2739   -0.0577    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1556   -0.2957    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4091    0.7464    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  6  1  1  0      \r\n  1  2  1  0      \r\n  2  7  1  0      \r\n  6  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  2  5  1  0      \r\n  6  7  1  0      \r\nM  END\r\n	templates/40b54210536082e5637d96b412abdd9bdcc0730ae82aa11df85e7c1116a5e32b.png	icons_small_29749abe5a22a4672ef13e6acc7ec09744d1eb9b437d2484697f7723e28b27db20160826-27944-3ghovk		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	29749abe5a22a4672ef13e6acc7ec09744d1eb9b437d2484697f7723e28b27db20160826-27944-3ghovk.png	image/png	3488	2016-08-26 14:11:37
48	\N	\N	_12	\r\n  Ketcher 07261614192D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n   -0.7951   -0.6392    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3797    1.1187    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4074   -0.0532    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3797    0.2937    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0357   -0.3987    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0357    0.5677    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9904   -0.0517    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6989   -0.5663    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2805   -1.1187    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2805    0.2194    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  5  1  1  0      \r\n  6  2  1  0      \r\n  4  2  1  0      \r\n  3  4  1  0      \r\n  5  6  1  0      \r\n  4  7  1  0      \r\n  5  8  1  0      \r\n  7  9  1  0      \r\n  8  9  1  0      \r\n  3 10  1  0      \r\n  1 10  1  0      \r\nM  END\r\n	templates/647153c07c3bd30ea778b61bac282ed29b81a324c19e468284ca9b9fe9791f31.png	icons_small_6bf957cf237b8f879519d36d9c60d56ad19f595879fd7126a6522ddb912d5f2320160826-27944-155bttq		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	6bf957cf237b8f879519d36d9c60d56ad19f595879fd7126a6522ddb912d5f2320160826-27944-155bttq.png	image/png	4371	2016-08-26 14:11:38
51	\N	\N	_15	\r\n  Ketcher 07261614192D\r\n\r\n 11 12  0  0  0  0  0  0  0  0999 V2000\r\n   -0.8136   -0.7751    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4315    1.2110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4940   -0.1664    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4315    0.2419    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0581   -0.5717    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0581    0.5630    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1492   -0.1649    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7555   -0.7751    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4529   -0.2971    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9880    0.1838    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4529   -1.2110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  5  1  1  0      \r\n  6  2  1  0      \r\n  4  2  1  0      \r\n  3  4  1  0      \r\n  5  6  1  0      \r\n  4  7  1  0      \r\n  5  8  1  0      \r\n  1  9  1  0      \r\n  3 10  1  0      \r\n  9 10  1  0      \r\n  8 11  1  0      \r\n  7 11  1  0      \r\nM  END\r\n	templates/93e092217910cd241403a28127874484be3ce37ebcafc92f655843f444e6e934.png	icons_small_a504a58b7085e663674962909dcf39371a04b182d77202e3f8d0d9bb44b4415020160826-27944-tfdr0f		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	a504a58b7085e663674962909dcf39371a04b182d77202e3f8d0d9bb44b4415020160826-27944-tfdr0f.png	image/png	4358	2016-08-26 14:11:38
54	\N	\N	_18	\r\n  Ketcher 07261614192D\r\n\r\n  8  9  0  0  0  0  0  0  0  0999 V2000\r\n   -0.6350   -0.8372    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3299   -0.4387    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7036    0.0591    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3299   -0.8372    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1679   -0.2927    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7066    0.0518    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0861   -0.4898    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4540    0.8372    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  7  1  1  0      \r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  5  1  0      \r\n  6  8  1  0      \r\n  7  4  1  0      \r\n  6  4  1  0      \r\n  5  6  1  0      \r\n  7  8  1  0      \r\nM  END\r\n	templates/b751d406017a09c642cfd574d8b68d04ef6ef1de21252bb3ac940ce639f0e6a7.png	icons_small_c6482f75c97ad5881e2c53fcda5398aa64fb5c533096ed66dbad9f9e9c6dc9a120160826-27944-aipqiq		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	c6482f75c97ad5881e2c53fcda5398aa64fb5c533096ed66dbad9f9e9c6dc9a120160826-27944-aipqiq.png	image/png	4028	2016-08-26 14:11:38
58	\N	\N	_22	\r\n  Ketcher 07261614192D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n    0.1713   -0.2471    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5999   -0.5401    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3638   -0.2267    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7603    0.1888    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2661   -0.0445    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4658    0.3390    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3171    1.0912    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.2078   -0.0226    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9294   -0.5722    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3638   -1.0912    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  7  1  0      \r\n  6  7  1  0      \r\n  6  8  1  0      \r\n  1  9  1  0      \r\n  8 10  1  0      \r\n  9 10  1  0      \r\nM  END\r\n	templates/55b7a572e8ac8c9d9acf166f0f7043559f8eabe921bee1f7b3d311536cc1f262.png	icons_small_a5c0553f0fe569d5bf848d4c6136664322afcd7b9b93f77ea9fc490a6e58a06a20160826-27944-o6c6vs		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	a5c0553f0fe569d5bf848d4c6136664322afcd7b9b93f77ea9fc490a6e58a06a20160826-27944-o6c6vs.png	image/png	4259	2016-08-26 14:11:39
60	\N	\N	_24	\r\n  Ketcher 07261614192D\r\n\r\n 10 11  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4290    0.4115    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4290   -0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7152   -0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    0.4115    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7152    0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7138   -0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4290   -0.4130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4290    0.4115    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7138    0.8252    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n  5 10  1  0      \r\nM  END\r\n	templates/a810497c826666ed0bbc43426748a7c89968b8f54e109bbf3b398a1ae07edfed.png	icons_small_8eccfdb39836d8eef9ac21e270bd915d5963a73afd4a38b5fee836901617b9b020160826-27944-1f4s6s4		2016-08-22 12:10:20	\N	2016-08-22 12:10:20	2016-11-30 09:46:32	2	approved	8eccfdb39836d8eef9ac21e270bd915d5963a73afd4a38b5fee836901617b9b020160826-27944-1f4s6s4.png	image/png	3155	2016-08-26 14:11:39
65	\N	\N	7 Cs	\r\n  Ketcher 07261614192D\r\n\r\n  7  7  0  0  0  0  0  0  0  0999 V2000\r\n   -0.9036    0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9036   -0.4125    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2586   -0.9269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5457   -0.7433    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9036    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5457    0.7433    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2586    0.9269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  1  1  0      \r\nM  END\r\n	templates/d073d0a484756905a82721517e622f040faf81f3cdca36c45af3aa37650cec72.png	icons_small_88c04cedef07523672bbcac7b906a3e32f3ac6c3a1544042ef81dbe8fa4ac7cb20160826-27944-kq9uoz		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	88c04cedef07523672bbcac7b906a3e32f3ac6c3a1544042ef81dbe8fa4ac7cb20160826-27944-kq9uoz.png	image/png	3811	2016-08-26 14:11:40
67	\N	\N	9 Cs	\r\n  Ketcher 07261614192D\r\n\r\n  9  9  0  0  0  0  0  0  0  0999 V2000\r\n    0.4124   -1.1736    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4142   -1.1736    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0428   -0.6431    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1881    0.1708    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7739    0.8829    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0018    1.1736    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7757    0.8956    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1881    0.1817    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0355   -0.6286    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  1  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  2  9  1  0      \r\nM  END\r\n	templates/491edd1a58f8a49cd96f36c1474f4d583d6785ca47942dbf298cc1a17dcac9e9.png	icons_small_ab7946fd089a7712ce835f825145bd888fbaadeb44a38eb6007b0752a95cbf7120160826-27944-1y6b187		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	ab7946fd089a7712ce835f825145bd888fbaadeb44a38eb6007b0752a95cbf7120160826-27944-1y6b187.png	image/png	3750	2016-08-26 14:11:40
68	\N	\N	10 Cs	\r\n  Ketcher 07261614192D\r\n\r\n 10 10  0  0  0  0  0  0  0  0999 V2000\r\n    0.4166   -1.2760    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4084   -1.2760    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0807   -0.7879    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3282   -0.0014    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0752    0.7837    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4125    1.2760    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4125    1.2760    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0739    0.7824    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3282   -0.0027    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1069   -0.7975    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  1  3  1  0      \r\n  3  4  1  0      \r\n  4  5  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n  2 10  1  0      \r\nM  END\r\n	templates/500e2e926190e97487ce914fb7efda14a42b9e8cedea7196bc181423adde2338.png	icons_small_4c1bd8610547c58769f91fed45211f23e7a8a2ccd8dcdcad45a391ffaac5f49120160826-27944-ryneri		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	4c1bd8610547c58769f91fed45211f23e7a8a2ccd8dcdcad45a391ffaac5f49120160826-27944-ryneri.png	image/png	3987	2016-08-26 14:11:37
70	\N	\N	_13	\r\n  Ketcher 07261614192D\r\n\r\n  9  9  0  0  0  0  0  0  0  0999 V2000\r\n   -1.3487    0.4108    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3487   -0.4142    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6355   -0.8256    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0810   -0.4142    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0810    0.4108    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6355    0.8256    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8658   -0.6679    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3487    0.0006    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8658    0.6668    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  5  6  1  0      \r\n  1  6  1  0      \r\n  4  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  5  9  1  0      \r\nM  END\r\n	templates/978065750a60b9ad90c6ebcd668059623eeb9a5c2d621c0443413f69da8c8e51.png	icons_small_e4242d4c5a6c7b6f8b2c6a4d7c0dcf648a34f5fdef50a483f5a06b83886f053120160826-27944-1ceo4n0		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	e4242d4c5a6c7b6f8b2c6a4d7c0dcf648a34f5fdef50a483f5a06b83886f053120160826-27944-1ceo4n0.png	image/png	3683	2016-08-26 14:11:38
72	\N	\N	_15	\r\n  Ketcher 07261614192D\r\n\r\n 11 11  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4283   -0.0067    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4283    0.8170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7144    1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0006    0.8170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7144   -0.4203    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7133    1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4283    0.8170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4283   -0.0067    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7133   -0.4203    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5183   -1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5340   -1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  1  5  1  0      \r\n  4  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n  5 11  1  0      \r\nM  END\r\n	templates/e1cf8fd005013c081007c85511cfb8cc43fe18041f0525a956769bbe099205c1.png	icons_small_a684460336c62f4094259a73240bc5f9b4073a52290dc12a03a49240bad0c31720160826-27944-aiijq0		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	a684460336c62f4094259a73240bc5f9b4073a52290dc12a03a49240bad0c31720160826-27944-aiijq0.png	image/png	3293	2016-08-26 14:11:38
73	\N	\N	_16	\r\n  Ketcher 07261614192D\r\n\r\n 12 12  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4295   -0.2071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4295   -1.0321    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7153   -1.4440    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000   -1.0321    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7153    0.2071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7141   -1.4440    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4295   -1.0321    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4295   -0.2071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7141    0.2071    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7141    1.0321    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000    1.4440    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7141    1.0321    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  1  5  1  0      \r\n  4  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n 11 12  1  0      \r\n  5 12  1  0      \r\nM  END\r\n	templates/e47795ab3bb739d1b92acfae3d3c5811d46a05b542426d915d6e880b063466e8.png	icons_small_eb4cd35b1089d6c451e778ff96290133a8cad665c0f069ade0679345e50cfdd320160826-27944-5wecok		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	eb4cd35b1089d6c451e778ff96290133a8cad665c0f069ade0679345e50cfdd320160826-27944-5wecok.png	image/png	3146	2016-08-26 14:11:38
75	\N	\N	_18	\r\n  Ketcher 07261614192D\r\n\r\n 14 14  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4301    0.4107    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4301   -0.4143    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7160   -0.8268    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7160    0.8250    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7142   -0.8268    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4301   -0.4143    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4301    0.4107    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7142    0.8250    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7142   -1.6518    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000   -2.0625    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7142   -1.6518    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7142    1.6500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7142    1.6500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0000    2.0625    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  1  4  1  0      \r\n  5  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8 13  1  0      \r\n  4 12  1  0      \r\n  3  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n  5 11  1  0      \r\n 14 12  1  0      \r\n 13 14  1  0      \r\nM  END\r\n	templates/a18edbe4aa455f3a95bcf17ef407b50d8956b02eb3ffcb9a8d72e7bf22a5f6d5.png	icons_small_f770063b99dedb17eac54faa263e78c364e4ba43accedb68e548afa4757cd54d20160826-27944-1gc0p9f		2016-08-22 12:18:57	\N	2016-08-22 12:18:57	2016-11-30 09:46:33	15	approved	f770063b99dedb17eac54faa263e78c364e4ba43accedb68e548afa4757cd54d20160826-27944-1gc0p9f.png	image/png	2998	2016-08-26 14:11:39
77	\N	\N	Cycloalkane_12 Cs	\r\n  ChemDraw08271621272D\r\n\r\n 11 11  0  0  0  0  0  0  0  0999 V2000\r\n   -1.4283   -0.0067    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4283    0.8170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7144    1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0006    0.8170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7144   -0.4203    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7133    1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4283    0.8170    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4283   -0.0067    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7133   -0.4203    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5183   -1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5340   -1.2294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  3  4  1  0      \r\n  1  5  1  0      \r\n  4  6  1  0      \r\n  6  7  1  0      \r\n  7  8  1  0      \r\n  8  9  1  0      \r\n  9 10  1  0      \r\n 10 11  1  0      \r\n  5 11  1  0      \r\nM  END\r\n	\N	icons_small_17ba56a118a1f8662040f342c0689a3177826c55b59c5679a15de2e4235caafe20160829-25371-ren4wu		2016-08-29 12:02:51	\N	2016-08-29 12:02:51	2016-11-30 09:46:33	15	approved	17ba56a118a1f8662040f342c0689a3177826c55b59c5679a15de2e4235caafe20160829-25371-ren4wu.png	image/png	3293	2016-08-29 12:03:28
83	\N	\N	Cytosine (DNA) Nucleoside	\r\n  ChemDraw08271621392D\r\n\r\n  0  0  0     0  0              0 V3000\r\nM  V30 BEGIN CTAB\r\nM  V30 COUNTS 21 22 0 0 1\r\nM  V30 BEGIN ATOM\r\nM  V30 1 C -1.042836 -2.133784 0.000000 0\r\nM  V30 2 C 0.344690 -2.133784 0.000000 0\r\nM  V30 3 O -0.350497 -1.236020 0.000000 0\r\nM  V30 4 C -1.472816 -1.649943 0.000000 0\r\nM  V30 5 H 0.344690 -2.679001 0.000000 0\r\nM  V30 6 O -1.042836 -2.679001 0.000000 0\r\nM  V30 7 H 0.344690 -1.708245 0.000000 0\r\nM  V30 8 H -1.042836 -1.708245 0.000000 0\r\nM  V30 9 H 0.766014 -2.358339 0.000000 0\r\nM  V30 10 C -1.472816 -0.988235 0.000000 0\r\nM  V30 11 H -1.472816 -2.358339 0.000000 0\r\nM  V30 12 O -2.188499 -0.574198 0.000000 0\r\nM  V30 13 C 0.766014 -1.649943 0.000000 0\r\nM  V30 14 C 0.043043 1.499860 0.000000 0\r\nM  V30 15 C 0.043043 0.674860 0.000000 0\r\nM  V30 16 N 0.757246 0.260937 0.000000 0\r\nM  V30 17 C 1.472930 0.674860 0.000000 0\r\nM  V30 18 N 1.472930 1.499860 0.000000 0\r\nM  V30 19 C 0.757246 1.912303 0.000000 0\r\nM  V30 20 N 0.757246 2.679001 0.000000 0\r\nM  V30 21 O 2.188499 0.260937 0.000000 0\r\nM  V30 END ATOM\r\nM  V30 BEGIN BOND\r\nM  V30 1 1 1 2 CFG=1\r\nM  V30 2 1 3 4\r\nM  V30 3 1 4 1 CFG=1\r\nM  V30 4 1 2 5\r\nM  V30 5 1 1 6\r\nM  V30 6 1 2 7\r\nM  V30 7 1 1 8\r\nM  V30 8 1 4 10\r\nM  V30 9 1 4 11\r\nM  V30 10 1 10 12\r\nM  V30 11 2 14 15\r\nM  V30 12 1 15 16\r\nM  V30 13 1 16 17\r\nM  V30 14 1 17 18\r\nM  V30 15 2 18 19\r\nM  V30 16 1 14 19\r\nM  V30 17 1 19 20\r\nM  V30 18 1 13 16\r\nM  V30 19 2 17 21\r\nM  V30 20 1 13 2 CFG=1\r\nM  V30 21 1 3 13\r\nM  V30 22 1 9 13\r\nM  V30 END BOND\r\nM  V30 END CTAB\r\nM  END\r\n	\N	icons_small_b3c1634a61de31a2cd6e56b6e5cebf1ba5e070c92b4b7d5fc0658babf8a408a720160830-29185-1i9smys		2016-08-30 05:18:18	\N	2016-08-30 05:18:18	2017-10-01 13:34:38	3	approved	b3c1634a61de31a2cd6e56b6e5cebf1ba5e070c92b4b7d5fc0658babf8a408a720160830-29185-1i9smys.png	image/png	6355	2016-08-30 05:18:18
90	\N	\N	Paracyclophane 1a	\r\n  Ketcher 05191712572D 1   1.00000     0.00000     0\r\n\r\n 16 18  0     0  0            999 V2000\r\n   -0.5525    1.6412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1082    1.1377    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5525    0.5231    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5590    0.5231    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1148    1.1377    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5590    1.6412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5525   -0.3269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0690   -0.8500    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5525   -1.4450    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5590   -1.4450    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1148   -0.8303    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5590   -0.3269    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3241   -0.4381    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3241   -2.0204    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3241    2.0204    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3241    0.4381    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  2  0     0  0\r\n  2  3  1  1     0  0\r\n  3  4  2  0     0  0\r\n  5  4  1  1     0  0\r\n  5  6  2  0     0  0\r\n  6  1  1  0     0  0\r\n  7  8  2  0     0  0\r\n  8  9  1  1     0  0\r\n  9 10  2  0     0  0\r\n 11 10  1  1     0  0\r\n 11 12  2  0     0  0\r\n 12  7  1  0     0  0\r\n  3 13  1  1     0  0\r\n  9 14  1  1     0  0\r\n  6 15  1  0     0  0\r\n 12 16  1  0     0  0\r\n 16 15  1  0     0  0\r\n 14 13  1  1     0  0\r\nM  END\r\n> <BoldBondsList>\r\n12 13 17\r\n$$$$\r\n\r\n	\N	icons_small_cc767b4bd46e645ca1f18388974170d623adfebc1f7beb9b1503d094b7e7e3bc		2016-08-30 06:15:56	\N	2016-08-30 06:15:56	2017-05-19 10:58:00	14	approved	cc767b4bd46e645ca1f18388974170d623adfebc1f7beb9b1503d094b7e7e3bc.png	image/png	37682	2017-05-19 10:57:59
94	\N	\N	Fullerenes Schlegel_1	\n  ChemDraw08271622552D\r\n\r\n 60 90  0  0  0  0  0  0  0  0999 V2000\r\n    0.0301    0.5989    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5415    0.3016    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5398   -0.2899    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0266   -0.5841    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4848   -0.2869    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4830    0.3047    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0547    0.5959    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5661    0.2986    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5643   -0.2929    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0512   -0.5871    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9944    0.6019    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9927    1.1935    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4795    1.4877    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0319    1.1904    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0249   -1.1756    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4882   -1.4699    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9996   -1.1726    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9979   -0.5811    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3548    0.0028    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7300    1.1840    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7165   -1.1777    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0135   -1.6892    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0329    1.6921    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.9463    0.0007    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4097    1.6130    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1396    2.1028    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5556    2.0450    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6129   -2.0481    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1741   -2.0809    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4404   -1.5671    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1292    0.4798    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.4118    0.0002    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.1264   -0.4773    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.2246    0.8954    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.2246   -0.9053    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9351    1.4797    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3709    2.3979    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3340   -2.3979    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.9490   -1.4715    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.8162   -0.9053    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.8162    0.8954    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.9693   -1.4767    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.9693    1.4667    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -3.3875   -1.8950    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -3.3875    1.8850    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.2448   -1.9838    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6298   -2.9102    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.8162   -1.8307    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2115   -3.3285    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.3875   -1.9838    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0584   -3.8998    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6666    2.9102    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.2308    1.9920    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2483    3.3285    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.8022    1.8389    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0952    3.8998    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    3.3736    1.9920    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2643    2.3291    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3182   -2.3024    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.6915    0.0026    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  0      \r\n  4  5  2  0      \r\n  5  6  1  0      \r\n  6  1  2  0      \r\n  2  7  1  0      \r\n  7  8  2  0      \r\n  8  9  1  0      \r\n  9 10  2  0      \r\n 10  3  1  0      \r\n  6 11  1  0      \r\n 11 12  2  0      \r\n 12 13  1  0      \r\n 13 14  2  0      \r\n 14  1  1  0      \r\n  4 15  1  0      \r\n 15 16  2  0      \r\n 16 17  1  0      \r\n 17 18  2  0      \r\n 18  5  1  0      \r\n 11 19  1  0      \r\n 19 18  1  0      \r\n 14 20  1  0      \r\n 20  7  1  0      \r\n 15 21  1  0      \r\n 21 10  1  0      \r\n 21 22  2  0      \r\n 20 23  2  0      \r\n 19 24  2  0      \r\n 26 27  1  0      \r\n 28 29  1  0      \r\n 29 30  1  0      \r\n 30 17  1  0      \r\n 31 32  1  0      \r\n 32 33  1  0      \r\n 25 34  2  0      \r\n 26 25  1  0      \r\n 31 36  2  0      \r\n 23 36  1  0      \r\n 37 27  2  0      \r\n 28 38  2  0      \r\n 39 33  2  0      \r\n 35 40  1  0      \r\n 34 41  1  0      \r\n 40 41  1  0      \r\n 40 42  2  0      \r\n 41 43  2  0      \r\n 39 46  1  0      \r\n 38 47  1  0      \r\n 46 47  1  0      \r\n 46 48  2  0      \r\n 47 49  2  0      \r\n 48 50  1  0      \r\n 49 51  1  0      \r\n 50 51  1  0      \r\n 45 44  1  0      \r\n 51 44  2  0      \r\n 37 52  1  0      \r\n 36 53  1  0      \r\n 52 53  1  0      \r\n 52 54  2  0      \r\n 53 55  2  0      \r\n 56 57  1  0      \r\n 57 50  2  0      \r\n 56 45  2  0      \r\n 26 58  2  0      \r\n 43 58  1  0      \r\n 54 58  1  0      \r\n 29 59  2  0      \r\n 49 59  1  0      \r\n 59 42  1  0      \r\n 32 60  2  0      \r\n 55 60  1  0      \r\n 60 48  1  0      \r\n 35 30  2  0      \r\n 27 13  1  0      \r\n 37 23  1  0      \r\n 44 42  1  0      \r\n 56 54  1  0      \r\n 45 43  1  0      \r\n 55 57  1  0      \r\n 24 34  1  0      \r\n 25 12  1  0      \r\n 24 35  1  0      \r\n 16 28  1  0      \r\n 22 39  1  0      \r\n  9 33  1  0      \r\n 22 38  1  0      \r\n  8 31  1  0      \r\nM  END\r\n	\N	icons_small_2ef8b268c615c07aa6a7f0e2eb96d4095e7e1fbe14dc9bb6c76199e044b8de1f20160830-29185-1hy6hbo		2016-08-30 06:50:33	\N	2016-08-30 06:50:33	2016-11-30 09:46:34	16	approved	2ef8b268c615c07aa6a7f0e2eb96d4095e7e1fbe14dc9bb6c76199e044b8de1f20160830-29185-1hy6hbo.png	image/png	13533	2016-08-30 06:50:33
96	\N	\N	_4	\r\n  Ketcher 07261614192D\r\n\r\n 11 10  0  0  0  0  0  0  0  0999 V2000\r\n    0.0000    0.7557    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000    0.3778    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3779    0.3778    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3779    0.3778    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000   -0.3778    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3779    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3779    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000   -0.7557    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3779   -0.3778    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3779   -0.3778    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  1  0      \r\n  2  4  1  0      \r\n  2  5  1  0      \r\n  5  6  1  0      \r\n  5  7  1  0      \r\n  5  8  1  0      \r\n  6  9  1  0      \r\n  6 10  1  0      \r\n  6 11  1  0      \r\nM  END\r\n	\N	icons_small_fcebad482bff73201e417cd856076032956c947fd40551183f30ad2f876b84f820160830-29185-1uwfpt6		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	fcebad482bff73201e417cd856076032956c947fd40551183f30ad2f876b84f820160830-29185-1uwfpt6.png	image/png	5787	2016-08-30 06:51:27
102	\N	\N	_10	\r\n  Ketcher 07261614192D\r\n\r\n 12 12  0  0  1  0  0  0  0  0999 V2000\r\n   -0.3578    0.2863    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7634    0.4294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7634   -0.6680    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7634    0.4294    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7634   -0.6680    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3578    0.6680    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3578    0.6680    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3578   -0.0477    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7634   -0.1431    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7634   -0.1431    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3578    0.2863    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3578   -0.0477    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n 11  1  1  0      \r\n 11  9  1  1      \r\n  1 10  1  1      \r\n  9  2  1  0      \r\n  9  3  1  0      \r\n 10  4  1  0      \r\n 10  5  1  0      \r\n  1  6  1  0      \r\n 11  7  1  0      \r\n  1  8  1  0      \r\n  9 10  1  1      \r\n 11 12  1  0      \r\nM  END\r\n	\N	icons_small_e38131bff524e93d404db227424fc2b81006a27a9022df62904ffc1fd73cbe4a20160830-29185-1vf40is		2016-08-30 06:51:27	\N	2016-08-30 06:51:27	2016-11-30 09:46:35	7	approved	e38131bff524e93d404db227424fc2b81006a27a9022df62904ffc1fd73cbe4a20160830-29185-1vf40is.png	image/png	7653	2016-08-30 06:51:27
104	\N	\N	_12	\r\n  Ketcher 07261614192D\r\n\r\n 12 12  0  0  1  0  0  0  0  0999 V2000\r\n    0.9996   -0.3056    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9996   -0.8774    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9851   -0.8774    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4784   -0.0129    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4784    0.0084    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0454    0.8774    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4715   -0.4042    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6117    0.2259    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0454    0.3056    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9851   -0.3056    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0891   -0.0376    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0891    0.5321    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  9  1  1  0      \r\n  1 11  1  1      \r\n 10 11  1  1      \r\n  1  2  1  0      \r\n 10  3  1  0      \r\n 10  4  1  0      \r\n  1  5  1  0      \r\n  9  6  1  0      \r\n 11  7  1  0      \r\n  9  8  1  0      \r\n  9 10  1  0      \r\n 11 12  1  0      \r\nM  END\r\n	\N	icons_small_8eda207a28f0a10976d16feabd10d41bfc09130e9f511cc7f6cc9c7f198a9aec20160830-29185-1dpw0gt		2016-08-30 06:51:27	\N	2016-08-30 06:51:28	2016-11-30 09:46:35	7	approved	8eda207a28f0a10976d16feabd10d41bfc09130e9f511cc7f6cc9c7f198a9aec20160830-29185-1dpw0gt.png	image/png	7201	2016-08-30 06:51:27
107	\N	\N	chair	\r\n  Ketcher 07261614192D\r\n\r\n 18 18  0  0  1  0  0  0  0  0999 V2000\r\n   -0.5516   -0.1999    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1555   -0.1455    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4103   -0.2934    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5506    0.1990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1345    0.1169    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4103    0.2934    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5516   -0.7725    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2949   -0.6675    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1555    0.4270    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8035   -0.1856    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4103   -0.8660    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5506    0.7715    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0974   -0.0024    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2529    0.6341    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1345   -0.4557    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8283    0.2362    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4103    0.8660    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0974   -0.0501    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  1      \r\n  1  6  1  0      \r\n  6 16  1  0      \r\n  6 17  1  0      \r\n  5  6  1  0      \r\n  1  7  1  0      \r\n  5 15  1  0      \r\n  2  8  1  0      \r\n  2  9  1  0      \r\n  5 14  1  0      \r\n  2  3  1  1      \r\n  4  5  1  0      \r\n  3 10  1  0      \r\n  4 12  1  0      \r\n  3 11  1  0      \r\n  4 13  1  0      \r\n  4  3  1  1      \r\n  1 18  1  0      \r\nM  END\r\n	\N	icons_small_3b4a17a29a61ae2cec1722e820e4053de3eba6f8c51632aef661a998bcec2e8c20160830-29185-1covfe		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2017-10-01 13:01:45	7	approved	3b4a17a29a61ae2cec1722e820e4053de3eba6f8c51632aef661a998bcec2e8c20160830-29185-1covfe.png	image/png	10063	2016-08-30 06:51:28
110	\N	\N	half chair	\r\n  Ketcher 07261614192D\r\n\r\n 15 15  0  0  1  0  0  0  0  0999 V2000\r\n   -0.0977   -0.0739    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.0977   -0.7363    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7653   -0.0739    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2496   -0.3509    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2496   -0.8521    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4511    0.2289    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4511    0.8521    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1524    0.3674    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9720    0.1307    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6165   -0.8077    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7984   -0.1876    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9213    0.4077    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9720   -0.4284    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3529   -0.3509    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5700    0.2672    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  3  1  1  0      \r\n  4  5  1  0      \r\n  6  7  1  0      \r\n  1  8  1  0      \r\n  6  9  1  0      \r\n 14 10  1  0      \r\n  4 11  1  0      \r\n  6  1  1  0      \r\n  3 14  1  1      \r\n  4 14  1  1      \r\n  6  4  1  1      \r\n  3 12  1  0      \r\n  3 13  1  0      \r\n 14 15  1  0      \r\nM  END\r\n	\N	icons_small_ed0812f97ccabe045a2e47155cdebf56b86f5e5a11000f4b09fbfe2dd304b8b520160830-29185-vivvu3		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2017-10-01 13:02:03	7	approved	ed0812f97ccabe045a2e47155cdebf56b86f5e5a11000f4b09fbfe2dd304b8b520160830-29185-vivvu3.png	image/png	9582	2016-08-30 06:51:28
111	\N	\N	_19	\r\n  Ketcher 07261614192D\r\n\r\n 15 15  0  0  1  0  0  0  0  0999 V2000\r\n    0.2919    0.0678    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1281    0.8708    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.6399    0.0418    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0324   -0.9659    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6307   -0.3359    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2919   -0.5046    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4664    0.9659    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.6399    0.0187    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4664    0.3936    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.2363    0.2408    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9768    0.1341    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9768    0.7064    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0324   -0.3936    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1281    0.2984    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6726    0.4354    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n 11 13  1  1      \r\n 11  9  1  0      \r\n  9  1  1  0      \r\n  1 14  1  0      \r\n 14  2  1  0      \r\n 14  3  1  0      \r\n 13  4  1  0      \r\n 13  5  1  0      \r\n  1  6  1  0      \r\n  9  7  1  0      \r\n 11  8  1  0      \r\n  9 10  1  0      \r\n 11 12  1  0      \r\n 14 13  1  1      \r\n  1 15  1  0      \r\nM  END\r\n	\N	icons_small_3622b04bd90b1f94b9832bca8a614e9ee22fc8867ea4ff623ec5508228ead71620160830-29185-g8hx7s		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2016-11-30 09:46:36	7	approved	3622b04bd90b1f94b9832bca8a614e9ee22fc8867ea4ff623ec5508228ead71620160830-29185-g8hx7s.png	image/png	8155	2016-08-30 06:51:28
113	\N	\N	_21	\r\n  Ketcher 07261614192D\r\n\r\n 18 18  0  0  1  0  0  0  0  0999 V2000\r\n    0.5516   -0.1999    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1555   -0.1455    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4103   -0.2934    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5506    0.1990    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1345    0.1169    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4103    0.2934    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5516   -0.7725    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.2949   -0.6675    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.1555    0.4270    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8035   -0.1856    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4103   -0.8660    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5506    0.7715    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0974   -0.0024    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.2529    0.6341    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1345   -0.4557    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8283    0.2362    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4103    0.8660    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0974   -0.0501    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  1      \r\n  1  6  1  0      \r\n  6 16  1  0      \r\n  6 17  1  0      \r\n  5  6  1  0      \r\n  1  7  1  0      \r\n  5 15  1  0      \r\n  2  8  1  0      \r\n  2  9  1  0      \r\n  5 14  1  0      \r\n  2  3  1  1      \r\n  4  5  1  0      \r\n  3 10  1  0      \r\n  4 12  1  0      \r\n  3 11  1  0      \r\n  4 13  1  0      \r\n  4  3  1  1      \r\n  1 18  1  0      \r\nM  END\r\n	\N	icons_small_815b1fbe45eaa139c9a17efa2679ee888937531f2f6ae6ebcb2aa2d9c2defa7520160830-29185-pexu4a		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2016-11-30 09:46:36	7	approved	815b1fbe45eaa139c9a17efa2679ee888937531f2f6ae6ebcb2aa2d9c2defa7520160830-29185-pexu4a.png	image/png	10155	2016-08-30 06:51:28
115	\N	\N	twist boat	\r\n  Ketcher 07261614192D\r\n\r\n 16 16  0  0  1  0  0  0  0  0999 V2000\r\n    0.8521    0.3843    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8542    0.7857    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3801    0.0337    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6281    0.8635    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3801    0.3376    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6830   -0.7940    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1031   -0.1364    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7038   -0.8635    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.4414   -0.0171    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5720   -0.4465    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.4642    0.2173    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5918   -0.2391    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8998    0.2578    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3781   -0.6986    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3324   -0.1706    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8998   -0.0939    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1 12  1  1      \r\n  1  9  1  0      \r\n 13  2  1  0      \r\n 13  3  1  0      \r\n  1  4  1  0      \r\n  1  5  1  0      \r\n 12  6  1  0      \r\n 12  7  1  0      \r\n 10  8  1  0      \r\n 13 10  1  0      \r\n 10  9  1  0      \r\n 10 11  1  0      \r\n 12 15  1  1      \r\n 13 15  1  1      \r\n 15 14  1  0      \r\n 15 16  1  0      \r\nM  END\r\n	\N	icons_small_bf8528ea0be06c7987094dd5bbb9039d436ea7ab4c59c4906bfc229ed596baeb20160830-29185-12ulew3		2016-08-30 06:51:28	\N	2016-08-30 06:51:28	2017-10-01 13:02:57	7	approved	bf8528ea0be06c7987094dd5bbb9039d436ea7ab4c59c4906bfc229ed596baeb20160830-29185-12ulew3.png	image/png	9429	2016-08-30 06:51:28
117	\N	\N	_25	\r\n  Ketcher 07261614192D\r\n\r\n 14 14  0  0  0  0  0  0  0  0999 V2000\r\n    1.5609    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.6062    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7946    0.7865    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7784   -0.7865    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5052    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.5505    0.0412    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7946    1.6110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5884    0.5650    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.5609   -0.7833    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.3159    0.3727    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.7784   -1.6110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.5868   -0.6216    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.3159   -0.3775    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.6062    0.8657    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  5  1  1  0      \r\n  6  2  1  0      \r\n  1  3  1  0      \r\n  2  4  1  0      \r\n  3  4  1  0      \r\n  5  6  2  0      \r\n  3  7  1  0      \r\n  3  8  1  0      \r\n  1  9  1  0      \r\n  1 10  1  0      \r\n  4 11  1  0      \r\n  4 12  1  0      \r\n  2 13  1  0      \r\n  2 14  1  0      \r\nM  END\r\n	\N	icons_small_76b3fd2357952c32cf74edba893f081b332a03d4b778f4b3de5be9b41d50169f20160830-29185-1ouj5d0		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	76b3fd2357952c32cf74edba893f081b332a03d4b778f4b3de5be9b41d50169f20160830-29185-1ouj5d0.png	image/png	6463	2016-08-30 06:51:29
119	\N	\N	_27	\r\n  Ketcher 07261614192D\r\n\r\n 14 14  0  0  1  0  0  0  0  0999 V2000\r\n   -0.5864    0.6202    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5853    0.6202    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1712    0.1916    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3415    0.0079    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3763   -0.3510    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.1712    0.1916    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3415    0.5463    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7764   -0.3098    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3763   -0.8893    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9062   -0.2539    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.7095    0.1916    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0519    0.8893    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.0529    0.8893    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.7095    0.1916    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  3  4  1  1      \r\n  4  5  1  1      \r\n  6  5  1  1      \r\n  1  6  2  0      \r\n  4  7  1  0      \r\n  4  8  1  0      \r\n  5  9  1  0      \r\n  5 10  1  0      \r\n  3 11  1  0      \r\n  2 12  1  0      \r\n  1 13  1  0      \r\n  6 14  1  0      \r\nM  END\r\n	\N	icons_small_9b49ffe4b381927e6054840f50ace4439577a13caa6fb11dc2d2fbd832d6377020160830-29185-csyvl9		2016-08-30 06:51:29	\N	2016-08-30 06:51:29	2016-11-30 09:46:36	7	approved	9b49ffe4b381927e6054840f50ace4439577a13caa6fb11dc2d2fbd832d6377020160830-29185-csyvl9.png	image/png	6864	2016-08-30 06:51:29
126	\N	\N	_34	\r\n  Ketcher 07261614192D\r\n\r\n 16 16  0  0  1  0  0  0  0  0999 V2000\r\n    1.7028   -0.4027    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.6822   -0.8561    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.4770    0.7316    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.8097   -0.1184    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.9718    0.4487    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.4889   -0.8561    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -2.4770    0.0602    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -1.3535    0.8561    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.6280   -0.1184    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.1949    0.1712    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0839   -0.5110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.8906   -0.5110    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.7796    0.1712    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.3779   -0.1739    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.0355   -0.2240    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8097    0.5529    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n 13 16  1  0      \r\n 15  1  1  0      \r\n 11  2  1  0      \r\n 16  3  1  0      \r\n 11 15  1  1      \r\n  4  5  2  0      \r\n  4 12  1  1      \r\n  5 10  1  0      \r\n 12  6  1  0      \r\n  4  7  1  0      \r\n  5  8  1  0      \r\n 10  9  1  0      \r\n 13 10  2  0      \r\n 11 12  2  0      \r\n 13 14  1  0      \r\n 15 16  2  0      \r\nM  END\r\n	\N	icons_small_ed03b96c64b908727e9fd9fb41910a5c5bdc30727f714bb00f1ddcb4160b4d3120160830-29185-pkghyf		2016-08-30 06:51:30	\N	2016-08-30 06:51:30	2016-11-30 09:46:36	7	approved	ed03b96c64b908727e9fd9fb41910a5c5bdc30727f714bb00f1ddcb4160b4d3120160830-29185-pkghyf.png	image/png	6713	2016-08-30 06:51:30
144	\N	\N	_18	\r\n  Ketcher 07261614192D\r\n\r\n  7  6  0  0  0  0  0  0  0  0999 V2000\r\n   -1.1129   -0.4664    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3987   -0.0554    0.0000 P   0  0  0  0  0  0  0  0  0  0  0  0\r\n   -0.3987    0.7696    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.3987   -0.2682    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0153   -0.7696    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.8403   -0.7696    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.1129    0.1428    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0      \r\n  2  3  2  0      \r\n  2  4  1  0      \r\n  2  5  1  0      \r\n  5  6  1  0      \r\n  4  7  1  0      \r\nM  END\r\n	\N	icons_small_8d9231171fda9a5838dbc55e9d9d63869d5446ce9ba9adb61a8733d3f4f080df20160830-1161-7dthwc		2016-08-30 08:35:19	\N	2016-08-30 08:35:19	2016-11-30 09:46:38	17	approved	8d9231171fda9a5838dbc55e9d9d63869d5446ce9ba9adb61a8733d3f4f080df20160830-1161-7dthwc.png	image/png	5253	2016-08-30 08:35:19
145	\N	\N	adamantane	\r\n  Ketcher 12131614342D 1   1.00000     0.00000     0\r\n\r\n 10 12  0     0  0            999 V2000\r\n    1.8005    0.7742    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.9127    1.2868    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4257    0.3991    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.8505   -0.1192    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    2.3674   -0.7518    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    1.4007   -0.4783    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0250    0.7743    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5656   -0.7518    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    0.5967   -0.4108    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  1  4  1  0     0  0\r\n  4  5  1  0     0  0\r\n  5  6  1  0     0  0\r\n  3  6  1  0     0  0\r\n  2  7  1  0     0  0\r\n  7  8  1  0     0  0\r\n  6  9  1  0     0  0\r\n  9  8  1  0     0  0\r\n  4 10  1  0     0  0\r\n 10  8  1  0     0  0\r\nM  END\r\n$$$$\r\n\r\n	\N	icons_small_58a6ff31d3f5cb0e92cb2fc19a3202ddd2ce6e66c496dc438dc2e24df64512db		2016-12-13 13:34:59	\N	2016-12-13 13:34:59	2016-12-13 13:34:59	2	approved	58a6ff31d3f5cb0e92cb2fc19a3202ddd2ce6e66c496dc438dc2e24df64512db.png	image/png	40873	2016-12-13 13:34:58
158	\N	\N	Benzophenone oxime resin	\r\n  Ketcher 10011716212D 1   1.00000     0.00000     0\r\n\r\n 16 17  0     0  0            999 V2000\r\n    5.1250   -5.1250    0.0000 R#  0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.2159   -5.1088    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.7159   -4.2428    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.7159   -4.2428    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    8.2160   -5.1088    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    7.7159   -5.9748    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    6.7159   -5.9748    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.2160   -5.1088    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.7160   -5.9748    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.7159   -5.9749    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   11.2160   -6.8409    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.7160   -7.7069    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.7160   -7.7069    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.2160   -6.8409    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\r\n    9.7160   -4.2428    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\r\n   10.7160   -4.2428    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\r\n  1  2  1  0     0  0\r\n  2  3  1  0     0  0\r\n  3  4  2  0     0  0\r\n  4  5  1  0     0  0\r\n  5  6  2  0     0  0\r\n  6  7  1  0     0  0\r\n  7  2  2  0     0  0\r\n  5  8  1  0     0  0\r\n  8  9  1  0     0  0\r\n  9 10  1  0     0  0\r\n 10 11  2  0     0  0\r\n 11 12  1  0     0  0\r\n 12 13  2  0     0  0\r\n 13 14  1  0     0  0\r\n 14  9  2  0     0  0\r\n  8 15  2  0     0  0\r\n 15 16  1  0     0  0\r\nM  RGP  1   1   1\r\nM  END\r\n> <PolymersList>\r\n0 \r\n$$$$\r\n\r\n	\N	icons_small_833c8d75197d7492f6bf327b820255e7f65bec46553918c77bd2001f0ba1aa69		2017-10-01 14:22:02	\N	2017-10-01 14:22:02	2017-10-01 14:22:02	18	approved	833c8d75197d7492f6bf327b820255e7f65bec46553918c77bd2001f0ba1aa69.png	image/png	40698	2017-10-01 14:22:01
\.


--
-- Data for Name: ketcherails_custom_templates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ketcherails_custom_templates (id, user_id, name, molfile, icon_path, sprite_class, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ketcherails_template_categories; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ketcherails_template_categories (id, name, created_at, updated_at, icon_file_name, icon_content_type, icon_file_size, icon_updated_at, sprite_class) FROM stdin;
2	Bicyclics	2016-07-26 12:14:07	2025-10-24 11:06:33.48799	Bicyclics.png	image/png	4212	2016-08-22 10:30:25	icons_small_Bicyclics
3	Nucleic Acids	2016-07-29 12:24:45	2025-10-24 11:06:34.022694	RNA_template_grau.png	image/png	1178	2016-08-30 10:19:38	icons_small_RNA_template_grau
4	Diverse heterocycles	2016-07-29 12:25:25	2025-10-24 11:06:24.666672	het.png	image/png	1083	2016-08-22 09:03:56	icons_small_het
5	Common bases	2016-07-29 12:26:28	2017-10-01 18:22:44	common_bases.png	image/png	772	2016-08-22 09:03:24	icons_small_common_bases
6	Amino Acids	2016-08-16 14:57:51	2025-10-24 11:06:33.768037	AA3.png	image/png	3064	2016-08-22 10:44:32	icons_small_AA3
9	Hexoses	2016-08-16 14:59:35	2016-11-30 09:46:29	hex.png	image/png	1119	2016-08-22 09:03:39	icons_small_hex
10	Metallocenes	2016-08-16 14:59:43	2016-11-30 09:46:29	metallocenes.png	image/png	1131	2016-08-22 09:02:32	icons_small_metallocenes
12	Polypeptides	2016-08-16 15:00:00	2016-11-30 09:46:29	Polypepides.png	image/png	3993	2016-08-22 09:30:34	icons_small_Polypepides
13	Polyhedra	2016-08-16 15:00:11	2016-11-30 09:46:29	Polyhedra2.png	image/png	3086	2016-08-22 09:27:04	icons_small_Polyhedra2
14	Paracyclophanes	2016-08-16 15:00:35	2025-10-24 11:06:30.222099	para2.png	image/png	12530	2016-08-22 09:02:50	icons_small_para2
15	Cycloalkanes	2016-08-22 06:33:10	2025-10-24 11:06:29.222543	cycloalkanes.png	image/png	1237	2016-08-22 09:03:12	icons_small_cycloalkanes
16	Schlegel	2016-08-22 06:37:36	2025-10-24 11:06:30.284267	Schlegel_grau.png	image/png	12100	2016-08-30 10:21:45	icons_small_Schlegel_grau
17	Functional group	2016-08-30 06:59:28	2025-10-24 11:06:33.428281	functional_groups_.png	image/png	3674	2016-08-30 10:16:00	icons_small_functional_groups_
1	Aromatics	2016-07-26 12:13:51	2025-10-24 11:06:26.729056	arom.png	image/png	1100	2016-08-22 09:02:10	icons_small_arom
7	Conformers	2016-08-16 14:58:29	2025-10-24 11:06:32.279001	confomers.png	image/png	3765	2016-08-22 10:11:10	icons_small_confomers
18	Solid Supports	2016-08-30 07:06:47	2025-10-24 11:06:34.506268	solid_2.png	image/png	6203	2016-08-30 09:15:07	icons_small_solid_2
\.


--
-- Data for Name: layer_tracks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.layer_tracks (id, identifier, name, label, description, properties, created_by, created_at, updated_by, updated_at, deleted_by, deleted_at) FROM stdin;
\.


--
-- Data for Name: layers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.layers (id, name, label, description, properties, identifier, created_by, created_at, updated_by, updated_at, deleted_by, deleted_at) FROM stdin;
\.


--
-- Data for Name: literals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.literals (id, literature_id, element_id, element_type, category, user_id, created_at, updated_at, litype) FROM stdin;
\.


--
-- Data for Name: literatures; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.literatures (id, title, url, created_at, updated_at, deleted_at, refs, doi, isbn) FROM stdin;
\.


--
-- Data for Name: matrices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.matrices (id, name, enabled, label, include_ids, exclude_ids, configs, created_at, updated_at, deleted_at) FROM stdin;
2	computedProp	f	computedProp	{}	{}	{"server": "", "hmac_secret": "", "allowed_uids": [], "receiving_secret": "", "parameter_descriptions": {"server": "address url of the service", "hmac_secret": "authorization key", "allowed_uids": "allowed list (array of integers) of user ids that can send requests to the computation service", "receiving_secret": "authorization key"}}	2024-01-23 13:44:00.891961	2024-01-23 13:44:00.894644	\N
3	chemdrawEditor	f	chemdrawEditor	{}	{}	{"editor": "chemdraw"}	2024-01-23 13:44:00.902169	2024-01-23 13:44:00.902169	\N
4	reactionPrediction	f	reactionPrediction	{}	{}	{"url": "", "port": ""}	2024-01-23 13:44:00.91361	2024-01-23 13:44:00.915788	\N
9	marvinjsEditor	f	marvinjsEditor	{}	{}	{"editor": "marvinjs"}	2024-01-23 13:44:01.51163	2024-01-23 13:44:01.51163	\N
10	nmrSim	f	nmrSim	{}	{}	{}	2024-01-23 13:44:02.095454	2024-01-23 13:44:02.095454	\N
12	scifinderN	f	scifinderN	{}	{}	{}	2024-01-23 13:44:02.416207	2024-01-23 13:44:02.416207	\N
13	userProvider	f	userProvider	{}	{}	{}	2024-01-23 13:44:02.664734	2024-01-23 13:44:02.664734	\N
14	commentActivation	f	commentActivation	{}	{}	{}	2024-01-23 13:44:02.672323	2024-01-23 13:44:02.672323	\N
6	genericElement	t	genericElement	{}	{}	{}	2024-01-23 13:44:01.319777	2024-01-24 07:05:04.210763	\N
8	genericDataset	t	genericDataset	{}	{}	{}	2024-01-23 13:44:01.408293	2024-01-24 07:05:09.339511	\N
7	segment	t	segment	{}	{}	{}	2024-01-23 13:44:01.38501	2024-01-24 07:05:14.327721	\N
5	sampleDecoupled	t	sampleDecoupled	{}	{}	{}	2024-01-23 13:44:01.055112	2024-01-24 07:05:24.958261	\N
11	ketcher2Editor	f	ketcher2Editor	{}	{}	{"editor": "ketcher2"}	2024-01-23 13:44:02.10268	2024-01-23 13:44:02.10268	\N
15	moleculeViewer	t	moleculeViewer	{}	{}	{}	2024-11-20 06:08:45.935531	2024-11-20 06:08:45.935531	\N
1	userLabel	f	userLabel	{}	{}	{}	2024-01-23 13:44:00.872595	2024-11-20 06:08:45.99473	2024-11-20 06:08:45.994721
16	fastInput	t	fastInput	{}	{}	{"cas_api_key": ""}	2025-11-13 04:53:16.676496	2025-11-13 04:53:16.676496	\N
\.


--
-- Data for Name: measurements; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.measurements (id, description, value, unit, deleted_at, well_id, sample_id, created_at, updated_at, source_type, source_id) FROM stdin;
\.


--
-- Data for Name: messages; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.messages (id, channel_id, content, created_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: metadata; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.metadata (id, collection_id, metadata, deleted_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: molecule_names; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.molecule_names (id, molecule_id, user_id, description, name, deleted_at, created_at, updated_at) FROM stdin;
1	1	\N	iupac_name	ammonia	\N	2024-01-23 15:17:17.540346	2024-01-23 15:17:17.540346
2	1	\N	iupac_name	azane	\N	2024-01-23 15:17:17.544501	2024-01-23 15:17:17.544501
3	1	\N	sum_formular	H3N	\N	2024-01-23 15:17:17.547954	2024-01-23 15:17:17.547954
4	2	\N	iupac_name	borane	\N	2024-11-20 06:12:29.253449	2024-11-20 06:12:29.253449
5	2	\N	sum_formular	BH3	\N	2024-11-20 06:12:29.254261	2024-11-20 06:12:29.254261
6	3	\N	iupac_name	1-methylnaphthalene	\N	2024-11-20 06:14:08.081838	2024-11-20 06:14:08.081838
7	3	\N	sum_formular	C11H10	\N	2024-11-20 06:14:08.082964	2024-11-20 06:14:08.082964
\.


--
-- Data for Name: molecules; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.molecules (id, inchikey, inchistring, density, molecular_weight, molfile, melting_point, boiling_point, sum_formular, names, iupac_name, molecule_svg_file, created_at, updated_at, deleted_at, is_partial, exact_molecular_weight, cano_smiles, cas, molfile_version) FROM stdin;
1	QGZKDVFQNNGYKY-UHFFFAOYSA-N	InChI=1S/H3N/h1H3	0	17.03052	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	\N	\N	H3N	{ammonia,azane}	azane	8ba2defe1807aabb304cf8a81fbc268d83bdc4e61fafb31166c71fbac4f43f490c9ba30d5741eacc5305a555edd5489a60e2c52c6e5931f5ee72d97bfd0002e0.svg	2024-01-23 15:17:17.520626	2024-01-23 15:17:17.520626	\N	f	17.026549101	N	\N	V2000
2	UORVGPXVDQYIDP-UHFFFAOYSA-N	InChI=1S/BH3/h1H3	0	13.83482	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e303030302042202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	\N	\N	BH3	{borane}	borane	33685bcfaf011a242c3dc29b5fb5d2889fd6041f0b3aae596af61cfa92581015e9f6adad8767f0ed8bdb482f030626a80b7a98ba188cd78c5db2070dbc75e7ba.svg	2024-11-20 06:12:29.251388	2024-11-20 06:12:29.251388	\N	f	14.032780496	B	\N	V2000
3	QPUYECUOLPXSFR-UHFFFAOYSA-N	InChI=1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3	0	142.19710000000003	\\x0a20204b657463686572203131323032343037313432442031202020312e30303030302020202020302e30303030302020202020300a0a2031312031322020302020202020302020302020202020202020202020203939392056323030300a20202020342e363530302020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832312020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d312e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a2020312020322020312020302020202020302020300a2020322020332020312020302020202020302020300a2020332020342020312020302020202020302020300a2020342020352020322020302020202020302020300a2020352020362020312020302020202020302020300a2020362020312020322020302020202020302020300a2020322020372020322020302020202020302020300a2020372020382020312020302020202020302020300a2020382020392020322020302020202020302020300a2020392031302020312020302020202020302020300a2031302020332020322020302020202020302020300a2020312031312020312020302020202020302020300a4d2020454e44	\N	\N	C11H10	{1-methylnaphthalene}	1-methylnaphthalene	84747fb6ed9df94a9198374ece7cfe5b819a8c05378b291369f3ae92aa2152920ed7db8105bade32eea32d4d17e6c558ab4490204b0caf8fb3eaa58ea563dbdf.svg	2024-11-20 06:14:08.078655	2024-11-20 06:14:08.078655	\N	f	142.07825032	Cc1cccc2c1cccc2	\N	V2000
\.


--
-- Data for Name: nmr_sim_nmr_simulations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.nmr_sim_nmr_simulations (id, molecule_id, path_1h, path_13c, source, deleted_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.notifications (id, message_id, user_id, is_ack, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: ols_terms; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ols_terms (id, owl_name, term_id, ancestry, ancestry_term_id, label, synonym, synonyms, "desc", metadata, is_enabled, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: pg_search_documents; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.pg_search_documents (id, content, searchable_type, searchable_id, created_at, updated_at) FROM stdin;
1	 MSU-1  H3N azane InChI=1S/H3N/h1H3 QGZKDVFQNNGYKY-UHFFFAOYSA-N N 	Sample	1	2024-01-23 15:17:46.459018	2024-01-23 15:17:46.459018
4	New Workflow API-WRK1	Labimotion::Element	3	2024-03-21 10:32:02.072924	2024-03-21 10:32:02.072924
5	New Workflow API-WRK2	Labimotion::Element	4	2024-03-21 10:41:42.5524	2024-03-21 10:41:42.5524
6	New Workflow API-WRK3	Labimotion::Element	5	2024-03-21 12:13:25.273091	2024-03-21 12:13:25.273091
7	 API-1  H3N azane InChI=1S/H3N/h1H3 QGZKDVFQNNGYKY-UHFFFAOYSA-N N 	Sample	2	2024-11-20 06:11:55.323941	2024-11-20 06:11:55.323941
8	 reactant  BH3 borane InChI=1S/BH3/h1H3 UORVGPXVDQYIDP-UHFFFAOYSA-N B 	Sample	3	2024-11-20 06:12:56.658354	2024-11-20 06:14:26.474173
9	API-R1-A API-3  C11H10 1-methylnaphthalene InChI=1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3 QPUYECUOLPXSFR-UHFFFAOYSA-N Cc1cccc2c1cccc2 	Sample	4	2024-11-20 06:14:15.818841	2024-11-20 06:14:26.501019
10	 API-R1 RInChI=1.00.1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3<>H3N/h1H3<>BH3/h1H3/d-	Reaction	1	2024-11-20 06:14:26.396616	2024-11-20 06:14:26.532335
12	API-R1-A API-3-1  C11H10 1-methylnaphthalene InChI=1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3 QPUYECUOLPXSFR-UHFFFAOYSA-N Cc1cccc2c1cccc2 	Sample	5	2025-11-13 04:54:36.638218	2025-11-13 04:54:36.638218
13	API-R2-A API-4  H3N azane InChI=1S/H3N/h1H3 QGZKDVFQNNGYKY-UHFFFAOYSA-N N 	Sample	6	2025-11-13 04:54:36.811726	2025-11-13 04:54:36.811726
11	 API-R2 RInChI=1.00.1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3<>H3N/h1H3/d+	Reaction	2	2025-11-13 04:54:36.271353	2025-11-13 04:54:36.895777
\.


--
-- Data for Name: predictions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.predictions (id, predictable_type, predictable_id, decision, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: private_notes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.private_notes (id, content, created_by, created_at, updated_at, noteable_id, noteable_type) FROM stdin;
\.


--
-- Data for Name: profiles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.profiles (id, show_external_name, user_id, deleted_at, created_at, updated_at, data, curation, show_sample_name, show_sample_short_label) FROM stdin;
3	f	4	\N	2024-01-24 07:01:45.783739	2024-01-24 07:01:45.783739	{}	2	f	f
2	f	3	\N	2024-01-23 15:12:19.925682	2024-01-23 15:15:49.216912	{"generic_admin": {"datasets": true, "elements": true, "segments": true}, "molecule_editor": true, "is_templates_moderator": true}	2	f	f
1	f	2	\N	2024-01-23 15:12:02.27083	2024-01-25 10:10:02.792749	{"chmo": [{"title": "1H nuclear magnetic resonance spectroscopy (1H NMR)", "value": " CHMO:0000593 | 1H nuclear magnetic resonance spectroscopy (1H NMR)", "search": "CHMO:0000593 | 1H nuclear magnetic resonance spectroscopy (1H NMR,1H NMR spectroscopy,1H nuclear magnetic resonance spectrometry,1H-NMR,1H-NMR spectrometry,1H-NMR spectroscopy,proton NMR,proton nuclear magnetic resonance spectroscopy)", "synonym": "1H NMR", "term_id": "CHMO:0000593", "owl_name": "chmo", "synonyms": ["1H NMR", "1H NMR spectroscopy", "1H nuclear magnetic resonance spectrometry", "1H-NMR", "1H-NMR spectrometry", "1H-NMR spectroscopy", "proton NMR", "proton nuclear magnetic resonance spectroscopy"]}, {"title": "13C nuclear magnetic resonance spectroscopy (13C NMR)", "value": " CHMO:0000595 | 13C nuclear magnetic resonance spectroscopy (13C NMR)", "search": "CHMO:0000595 | 13C nuclear magnetic resonance spectroscopy (13C NMR,13C NMR spectroscopy,13C nuclear magnetic resonance spectrometry,13C-NMR spectrometry,13C-NMR spectroscopy,C-NMR,carbon NMR)", "synonym": "13C NMR", "term_id": "CHMO:0000595", "owl_name": "chmo", "synonyms": ["13C NMR", "13C NMR spectroscopy", "13C nuclear magnetic resonance spectrometry", "13C-NMR spectrometry", "13C-NMR spectroscopy", "C-NMR", "carbon NMR"]}, {"title": "mass spectrometry (MS)", "value": " CHMO:0000470 | mass spectrometry (MS)", "search": "CHMO:0000470 | mass spectrometry (MS,mass spectroscopy)", "synonym": "MS", "term_id": "CHMO:0000470", "owl_name": "chmo", "synonyms": ["MS", "mass spectroscopy"]}, {"title": "elemental analysis (EA)", "value": " CHMO:0001075 | elemental analysis (EA)", "search": "CHMO:0001075 | elemental analysis (EA)", "synonym": "EA", "term_id": "CHMO:0001075", "owl_name": "chmo", "synonyms": ["EA"]}, {"title": "gas chromatography-mass spectrometry (GCMS)", "value": " CHMO:0000497 | gas chromatography-mass spectrometry (GCMS)", "search": "CHMO:0000497 | gas chromatography-mass spectrometry (GC MS,GC-MS,GC/MS,GCMS,gas chromatography mass spectrometry,gas chromatography mass spectroscopy,gas chromatography with mass spectrometric detection,gas chromatography-mass spectroscopy,gas chromatography/mass spectrometry)", "synonym": "GCMS", "term_id": "CHMO:0000497", "owl_name": "chmo", "synonyms": ["GC MS", "GC-MS", "GC/MS", "GCMS", "gas chromatography mass spectrometry", "gas chromatography mass spectroscopy", "gas chromatography with mass spectrometric detection", "gas chromatography-mass spectroscopy", "gas chromatography/mass spectrometry"]}, {"title": "high-performance liquid chromatography (HPLC)", "value": " CHMO:0001009 | high-performance liquid chromatography (HPLC)", "search": "CHMO:0001009 | high-performance liquid chromatography (HPLC,high performance liquid chromatography,high pressure liquid chromatography,high-pressure liquid chromatography)", "synonym": "HPLC", "term_id": "CHMO:0001009", "owl_name": "chmo", "synonyms": ["HPLC", "high performance liquid chromatography", "high pressure liquid chromatography", "high-pressure liquid chromatography"]}, {"title": "infrared absorption spectroscopy (IR)", "value": " CHMO:0000630 | infrared absorption spectroscopy (IR)", "search": "CHMO:0000630 | infrared absorption spectroscopy (IR,IR absorption spectrometry,IR absorption spectroscopy,IR spectrometry,IR spectrophotometry,IR spectroscopy,infra-red absorption spectrometry,infra-red absorption spectroscopy,infra-red spectrometry,infra-red spectrophotometry,infrared (IR) spectroscopy,infrared absorption spectrometry,infrared spectrometry,infrared spectrophotometry,infrared spectroscopy)", "synonym": "IR", "term_id": "CHMO:0000630", "owl_name": "chmo", "synonyms": ["IR", "IR absorption spectrometry", "IR absorption spectroscopy", "IR spectrometry", "IR spectrophotometry", "IR spectroscopy", "infra-red absorption spectrometry", "infra-red absorption spectroscopy", "infra-red spectrometry", "infra-red spectrophotometry", "infrared (IR) spectroscopy", "infrared absorption spectrometry", "infrared spectrometry", "infrared spectrophotometry", "infrared spectroscopy"]}, {"title": "thin-layer chromatography (TLC)", "value": " CHMO:0001007 | thin-layer chromatography (TLC)", "search": "CHMO:0001007 | thin-layer chromatography (TLC)", "synonym": "TLC", "term_id": "CHMO:0001007", "owl_name": "chmo", "synonyms": ["TLC"]}, {"title": "X-ray diffraction (XRD)", "value": " CHMO:0000156 | X-ray diffraction (XRD)", "search": "CHMO:0000156 | X-ray diffraction (X-Ray crystallographic analysis,X-ray analysis,X-ray crystallography,X-ray diffraction analysis,X-ray diffractometry,X-ray structure determination,XRD)", "synonym": "XRD", "term_id": "CHMO:0000156", "owl_name": "chmo", "synonyms": ["X-Ray crystallographic analysis", "X-ray analysis", "X-ray crystallography", "X-ray diffraction analysis", "X-ray diffractometry", "X-ray structure determination", "XRD"]}, {"title": "process", "value": " BFO:0000015 | process", "search": "BFO:0000015 | process", "synonym": null, "term_id": "BFO:0000015", "owl_name": "chmo", "synonyms": null}], "layout": {"try": 2, "sample": 1, "screen": 5, "reaction": 3, "cell_line": -1, "wellplate": 4, "research_plan": 6}, "generic_admin": {"datasets": true, "elements": true, "segments": true}, "converter_admin": false, "molecule_editor": false, "layout_detail_try": {"TrySeg1": 2, "analyses": 3, "properties": 1, "attachments": 4}, "layout_detail_sample": {"results": 5, "analyses": 1, "properties": 3, "references": 4, "qc_curation": 2, "measurements": -1}, "layout_detail_screen": {"analyses": 2, "properties": 1}, "is_templates_moderator": false, "layout_detail_reaction": {"scheme": 1, "analyses": 3, "properties": 2, "references": 4, "variations": 6, "green_chemistry": 5}, "layout_detail_wellplate": {"list": 4, "analyses": 2, "designer": 3, "properties": 1}, "default_structure_editor": "ketcher", "layout_detail_research_plan": {"analyses": 2, "references": 3, "attachments": 4, "research_plan": 1}}	2	f	f
7	f	8	\N	2024-02-16 08:53:15.389988	2024-02-16 08:53:15.389988	{}	2	f	f
6	f	7	\N	2024-02-16 08:52:48.565375	2024-03-21 12:13:12.53115	{"chmo": [{"title": "1H nuclear magnetic resonance spectroscopy (1H NMR)", "value": " CHMO:0000593 | 1H nuclear magnetic resonance spectroscopy (1H NMR)", "search": "CHMO:0000593 | 1H nuclear magnetic resonance spectroscopy (1H NMR,1H NMR spectroscopy,1H nuclear magnetic resonance spectrometry,1H-NMR,1H-NMR spectrometry,1H-NMR spectroscopy,proton NMR,proton nuclear magnetic resonance spectroscopy)", "synonym": "1H NMR", "term_id": "CHMO:0000593", "owl_name": "chmo", "synonyms": ["1H NMR", "1H NMR spectroscopy", "1H nuclear magnetic resonance spectrometry", "1H-NMR", "1H-NMR spectrometry", "1H-NMR spectroscopy", "proton NMR", "proton nuclear magnetic resonance spectroscopy"]}, {"title": "13C nuclear magnetic resonance spectroscopy (13C NMR)", "value": " CHMO:0000595 | 13C nuclear magnetic resonance spectroscopy (13C NMR)", "search": "CHMO:0000595 | 13C nuclear magnetic resonance spectroscopy (13C NMR,13C NMR spectroscopy,13C nuclear magnetic resonance spectrometry,13C-NMR spectrometry,13C-NMR spectroscopy,C-NMR,carbon NMR)", "synonym": "13C NMR", "term_id": "CHMO:0000595", "owl_name": "chmo", "synonyms": ["13C NMR", "13C NMR spectroscopy", "13C nuclear magnetic resonance spectrometry", "13C-NMR spectrometry", "13C-NMR spectroscopy", "C-NMR", "carbon NMR"]}, {"title": "mass spectrometry (MS)", "value": " CHMO:0000470 | mass spectrometry (MS)", "search": "CHMO:0000470 | mass spectrometry (MS,mass spectroscopy)", "synonym": "MS", "term_id": "CHMO:0000470", "owl_name": "chmo", "synonyms": ["MS", "mass spectroscopy"]}, {"title": "elemental analysis (EA)", "value": " CHMO:0001075 | elemental analysis (EA)", "search": "CHMO:0001075 | elemental analysis (EA)", "synonym": "EA", "term_id": "CHMO:0001075", "owl_name": "chmo", "synonyms": ["EA"]}, {"title": "gas chromatography-mass spectrometry (GCMS)", "value": " CHMO:0000497 | gas chromatography-mass spectrometry (GCMS)", "search": "CHMO:0000497 | gas chromatography-mass spectrometry (GC MS,GC-MS,GC/MS,GCMS,gas chromatography mass spectrometry,gas chromatography mass spectroscopy,gas chromatography with mass spectrometric detection,gas chromatography-mass spectroscopy,gas chromatography/mass spectrometry)", "synonym": "GCMS", "term_id": "CHMO:0000497", "owl_name": "chmo", "synonyms": ["GC MS", "GC-MS", "GC/MS", "GCMS", "gas chromatography mass spectrometry", "gas chromatography mass spectroscopy", "gas chromatography with mass spectrometric detection", "gas chromatography-mass spectroscopy", "gas chromatography/mass spectrometry"]}, {"title": "high-performance liquid chromatography (HPLC)", "value": " CHMO:0001009 | high-performance liquid chromatography (HPLC)", "search": "CHMO:0001009 | high-performance liquid chromatography (HPLC,high performance liquid chromatography,high pressure liquid chromatography,high-pressure liquid chromatography)", "synonym": "HPLC", "term_id": "CHMO:0001009", "owl_name": "chmo", "synonyms": ["HPLC", "high performance liquid chromatography", "high pressure liquid chromatography", "high-pressure liquid chromatography"]}, {"title": "infrared absorption spectroscopy (IR)", "value": " CHMO:0000630 | infrared absorption spectroscopy (IR)", "search": "CHMO:0000630 | infrared absorption spectroscopy (IR,IR absorption spectrometry,IR absorption spectroscopy,IR spectrometry,IR spectrophotometry,IR spectroscopy,infra-red absorption spectrometry,infra-red absorption spectroscopy,infra-red spectrometry,infra-red spectrophotometry,infrared (IR) spectroscopy,infrared absorption spectrometry,infrared spectrometry,infrared spectrophotometry,infrared spectroscopy)", "synonym": "IR", "term_id": "CHMO:0000630", "owl_name": "chmo", "synonyms": ["IR", "IR absorption spectrometry", "IR absorption spectroscopy", "IR spectrometry", "IR spectrophotometry", "IR spectroscopy", "infra-red absorption spectrometry", "infra-red absorption spectroscopy", "infra-red spectrometry", "infra-red spectrophotometry", "infrared (IR) spectroscopy", "infrared absorption spectrometry", "infrared spectrometry", "infrared spectrophotometry", "infrared spectroscopy"]}, {"title": "thin-layer chromatography (TLC)", "value": " CHMO:0001007 | thin-layer chromatography (TLC)", "search": "CHMO:0001007 | thin-layer chromatography (TLC)", "synonym": "TLC", "term_id": "CHMO:0001007", "owl_name": "chmo", "synonyms": ["TLC"]}, {"title": "X-ray diffraction (XRD)", "value": " CHMO:0000156 | X-ray diffraction (XRD)", "search": "CHMO:0000156 | X-ray diffraction (X-Ray crystallographic analysis,X-ray analysis,X-ray crystallography,X-ray diffraction analysis,X-ray diffractometry,X-ray structure determination,XRD)", "synonym": "XRD", "term_id": "CHMO:0000156", "owl_name": "chmo", "synonyms": ["X-Ray crystallographic analysis", "X-ray analysis", "X-ray crystallography", "X-ray diffraction analysis", "X-ray diffractometry", "X-ray structure determination", "XRD"]}, {"title": "process", "value": " BFO:0000015 | process", "search": "BFO:0000015 | process", "synonym": null, "term_id": "BFO:0000015", "owl_name": "chmo", "synonyms": null}], "layout": {"try": -2, "wrk": 1, "sample": 2, "screen": 5, "reaction": 3, "cell_line": -1, "wellplate": 4, "research_plan": 6}, "generic_admin": {"datasets": true, "elements": true, "segments": true}, "converter_admin": false, "molecule_editor": true, "layout_detail_sample": {"results": 5, "analyses": 2, "properties": 1, "references": 4, "qc_curation": 3}, "layout_detail_screen": {"analyses": 2, "properties": 1}, "is_templates_moderator": true, "layout_detail_reaction": {"scheme": 1, "analyses": 3, "properties": 2, "references": 4, "variations": 6, "green_chemistry": 5}, "layout_detail_wellplate": {"list": 4, "analyses": 2, "designer": 3, "properties": 1}, "default_structure_editor": "ketcher", "layout_detail_research_plan": {"analyses": 2, "references": 3, "attachments": 4, "research_plan": 1}}	2	f	f
8	f	9	\N	2024-09-27 09:11:56.606768	2024-09-27 09:11:56.606768	{"chmo": [{"title": "1H nuclear magnetic resonance spectroscopy (1H NMR)", "value": " CHMO:0000593 | 1H nuclear magnetic resonance spectroscopy (1H NMR)", "search": "CHMO:0000593 | 1H nuclear magnetic resonance spectroscopy (1H NMR,1H NMR spectroscopy,1H nuclear magnetic resonance spectrometry,1H-NMR,1H-NMR spectrometry,1H-NMR spectroscopy,proton NMR,proton nuclear magnetic resonance spectroscopy)", "synonym": "1H NMR", "term_id": "CHMO:0000593", "owl_name": "chmo", "synonyms": ["1H NMR", "1H NMR spectroscopy", "1H nuclear magnetic resonance spectrometry", "1H-NMR", "1H-NMR spectrometry", "1H-NMR spectroscopy", "proton NMR", "proton nuclear magnetic resonance spectroscopy"]}, {"title": "13C nuclear magnetic resonance spectroscopy (13C NMR)", "value": " CHMO:0000595 | 13C nuclear magnetic resonance spectroscopy (13C NMR)", "search": "CHMO:0000595 | 13C nuclear magnetic resonance spectroscopy (13C NMR,13C NMR spectroscopy,13C nuclear magnetic resonance spectrometry,13C-NMR spectrometry,13C-NMR spectroscopy,C-NMR,carbon NMR)", "synonym": "13C NMR", "term_id": "CHMO:0000595", "owl_name": "chmo", "synonyms": ["13C NMR", "13C NMR spectroscopy", "13C nuclear magnetic resonance spectrometry", "13C-NMR spectrometry", "13C-NMR spectroscopy", "C-NMR", "carbon NMR"]}, {"title": "mass spectrometry (MS)", "value": " CHMO:0000470 | mass spectrometry (MS)", "search": "CHMO:0000470 | mass spectrometry (MS,mass spectroscopy)", "synonym": "MS", "term_id": "CHMO:0000470", "owl_name": "chmo", "synonyms": ["MS", "mass spectroscopy"]}, {"title": "elemental analysis (EA)", "value": " CHMO:0001075 | elemental analysis (EA)", "search": "CHMO:0001075 | elemental analysis (EA)", "synonym": "EA", "term_id": "CHMO:0001075", "owl_name": "chmo", "synonyms": ["EA"]}, {"title": "gas chromatography-mass spectrometry (GCMS)", "value": " CHMO:0000497 | gas chromatography-mass spectrometry (GCMS)", "search": "CHMO:0000497 | gas chromatography-mass spectrometry (GC MS,GC-MS,GC/MS,GCMS,gas chromatography mass spectrometry,gas chromatography mass spectroscopy,gas chromatography with mass spectrometric detection,gas chromatography-mass spectroscopy,gas chromatography/mass spectrometry)", "synonym": "GCMS", "term_id": "CHMO:0000497", "owl_name": "chmo", "synonyms": ["GC MS", "GC-MS", "GC/MS", "GCMS", "gas chromatography mass spectrometry", "gas chromatography mass spectroscopy", "gas chromatography with mass spectrometric detection", "gas chromatography-mass spectroscopy", "gas chromatography/mass spectrometry"]}, {"title": "high-performance liquid chromatography (HPLC)", "value": " CHMO:0001009 | high-performance liquid chromatography (HPLC)", "search": "CHMO:0001009 | high-performance liquid chromatography (HPLC,high performance liquid chromatography,high pressure liquid chromatography,high-pressure liquid chromatography)", "synonym": "HPLC", "term_id": "CHMO:0001009", "owl_name": "chmo", "synonyms": ["HPLC", "high performance liquid chromatography", "high pressure liquid chromatography", "high-pressure liquid chromatography"]}, {"title": "infrared absorption spectroscopy (IR)", "value": " CHMO:0000630 | infrared absorption spectroscopy (IR)", "search": "CHMO:0000630 | infrared absorption spectroscopy (IR,IR absorption spectrometry,IR absorption spectroscopy,IR spectrometry,IR spectrophotometry,IR spectroscopy,infra-red absorption spectrometry,infra-red absorption spectroscopy,infra-red spectrometry,infra-red spectrophotometry,infrared (IR) spectroscopy,infrared absorption spectrometry,infrared spectrometry,infrared spectrophotometry,infrared spectroscopy)", "synonym": "IR", "term_id": "CHMO:0000630", "owl_name": "chmo", "synonyms": ["IR", "IR absorption spectrometry", "IR absorption spectroscopy", "IR spectrometry", "IR spectrophotometry", "IR spectroscopy", "infra-red absorption spectrometry", "infra-red absorption spectroscopy", "infra-red spectrometry", "infra-red spectrophotometry", "infrared (IR) spectroscopy", "infrared absorption spectrometry", "infrared spectrometry", "infrared spectrophotometry", "infrared spectroscopy"]}, {"title": "thin-layer chromatography (TLC)", "value": " CHMO:0001007 | thin-layer chromatography (TLC)", "search": "CHMO:0001007 | thin-layer chromatography (TLC)", "synonym": "TLC", "term_id": "CHMO:0001007", "owl_name": "chmo", "synonyms": ["TLC"]}, {"title": "X-ray diffraction (XRD)", "value": " CHMO:0000156 | X-ray diffraction (XRD)", "search": "CHMO:0000156 | X-ray diffraction (X-Ray crystallographic analysis,X-ray analysis,X-ray crystallography,X-ray diffraction analysis,X-ray diffractometry,X-ray structure determination,XRD)", "synonym": "XRD", "term_id": "CHMO:0000156", "owl_name": "chmo", "synonyms": ["X-Ray crystallographic analysis", "X-ray analysis", "X-ray crystallography", "X-ray diffraction analysis", "X-ray diffractometry", "X-ray structure determination", "XRD"]}, {"title": "process", "value": " BFO:0000015 | process", "search": "BFO:0000015 | process", "synonym": null, "term_id": "BFO:0000015", "owl_name": "chmo", "synonyms": null}], "layout": {"sample": 1, "screen": 4, "reaction": 2, "cell_line": -1000, "wellplate": 3, "research_plan": 5}, "converter_admin": false, "molecule_editor": false, "is_templates_moderator": false}	2	f	f
4	f	5	2024-11-20 06:08:45.949671	2024-02-16 08:50:38.515631	2024-02-16 08:50:38.515631	{}	2	f	f
5	f	6	2024-11-20 06:08:45.949671	2024-02-16 08:51:22.3029	2024-02-16 08:51:22.3029	{}	2	f	f
\.


--
-- Data for Name: reactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reactions (id, name, created_at, updated_at, description, timestamp_start, timestamp_stop, observation, purification, dangerous_products, tlc_solvents, tlc_description, rf_value, temperature, status, reaction_svg_file, solvent, deleted_at, short_label, created_by, role, origin, rinchi_string, rinchi_long_key, rinchi_short_key, rinchi_web_key, duration, rxno, conditions, variations, plain_text_description, plain_text_observation, gaseous, vessel_size, log_data) FROM stdin;
1		2024-11-20 06:14:26.377705	2024-11-20 06:15:51.753287	--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\nops:\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\n  insert: "\\n"\n			--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\nops:\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\n  insert: "\\n"\n	{}	{}			0	{"data": [], "userText": "", "valueUnit": "°C"}		ed612b54b097d204efc8df601ea8b808e3741b66b1ca286a3a9f32d781a71685.svg		\N	API-R1	7		{}	RInChI=1.00.1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3<>H3N/h1H3<>BH3/h1H3/d-	Long-RInChIKey=SA-BUHFF-QPUYECUOLPXSFR-UHFFFAOYSA-N--QGZKDVFQNNGYKY-UHFFFAOYSA-N--UORVGPXVDQYIDP-UHFFFAOYSA-N	Short-RInChIKey=SA-BUHFF-QPUYECUOLP-QGZKDVFQNN-UORVGPXVDQ-NUHFF-NUHFF-NUHFF-ZZZ	Web-RInChIKey=QIYMARWDEZAJTNBIR-NUHFFFADPSCTJSA				{"2eaad41c-1bec-480c-89ef-eca2702e4933": {"id": 2, "uuid": "2eaad41c-1bec-480c-89ef-eca2702e4933", "metadata": {"notes": "", "analyses": []}, "products": {"4": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": false, "materialType": "products", "vesselVolume": 0, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": null}, "yield": {"unit": null, "value": 0}, "amount": {"unit": "mol", "value": 0}}}, "solvents": {}, "reactants": {"3": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "BH3", "coefficient": 1, "isReference": false, "materialType": "reactants", "vesselVolume": 0, "molecularWeight": 13.83482}, "mass": {"unit": "g", "value": 0.022}, "amount": {"unit": "mol", "value": 0.0015901905481965069}, "equivalent": {"unit": null, "value": 0.13540885967435787}}}, "properties": {"duration": {"unit": "Second(s)", "value": 2}, "temperature": {"unit": "°C", "value": 2}}, "startingMaterials": {"2": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "H3N", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": 0, "molecularWeight": 17.03052}, "mass": {"unit": "g", "value": 0.2}, "amount": {"unit": "mol", "value": 0.011743622625733096}, "equivalent": {"unit": null, "value": null}}}}, "5c7e6ff4-9caa-43e6-9805-af4ebba87e40": {"id": 1, "uuid": "5c7e6ff4-9caa-43e6-9805-af4ebba87e40", "metadata": {"notes": "", "analyses": []}, "products": {"4": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": false, "materialType": "products", "vesselVolume": 0, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": null}, "yield": {"unit": null, "value": 0}, "amount": {"unit": "mol", "value": 0}}}, "solvents": {}, "reactants": {"3": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "BH3", "coefficient": 1, "isReference": false, "materialType": "reactants", "vesselVolume": 0, "molecularWeight": 13.83482}, "mass": {"unit": "g", "value": 0.022}, "amount": {"unit": "mol", "value": 0.0015901905481965069}, "equivalent": {"unit": null, "value": 0.0013540885967435786}}}, "properties": {"duration": {"unit": "Second(s)", "value": 2}, "temperature": {"unit": "°C", "value": 1}}, "startingMaterials": {"2": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "H3N", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": 0, "molecularWeight": 17.03052}, "mass": {"unit": "g", "value": 20}, "amount": {"unit": "mol", "value": 1.1743622625733097}, "equivalent": {"unit": null, "value": null}}}}}			f	{"unit": "ml", "amount": null}	{"h": [{"c": {"id": 1, "name": "", "role": "", "rxno": "", "origin": "{}", "status": "", "gaseous": false, "solvent": "", "duration": "", "rf_value": "0", "conditions": "", "created_at": "2024-11-20T06:14:26.377705", "created_by": 7, "deleted_at": null, "updated_at": "2024-11-20T06:15:51.753287", "variations": [{"id": 1, "notes": "", "analyses": [], "products": {"4": {"aux": {"purity": 1, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": false, "materialType": "products", "vesselVolume": 0, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": null}, "yield": {"unit": null, "value": 0}, "amount": {"unit": "mol", "value": 0}}}, "solvents": {}, "reactants": {"3": {"aux": {"purity": 1, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "BH3", "coefficient": 1, "isReference": false, "materialType": "reactants", "vesselVolume": 0, "molecularWeight": 13.83482}, "mass": {"unit": "g", "value": 0.022}, "amount": {"unit": "mol", "value": 0.0015901905481965069}, "equivalent": {"unit": null, "value": 0.0013540885967435786}}}, "properties": {"duration": {"unit": "Second(s)", "value": 2}, "temperature": {"unit": "°C", "value": 1}}, "startingMaterials": {"2": {"aux": {"purity": 1, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "H3N", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": 0, "molecularWeight": 17.03052}, "mass": {"unit": "g", "value": 20}, "amount": {"unit": "mol", "value": 1.1743622625733097}, "equivalent": {"unit": null, "value": null}}}}, {"id": 2, "notes": "", "analyses": [], "products": {"4": {"aux": {"purity": 1, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": false, "materialType": "products", "vesselVolume": 0, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": null}, "yield": {"unit": null, "value": 0}, "amount": {"unit": "mol", "value": 0}}}, "solvents": {}, "reactants": {"3": {"aux": {"purity": 1, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "BH3", "coefficient": 1, "isReference": false, "materialType": "reactants", "vesselVolume": 0, "molecularWeight": 13.83482}, "mass": {"unit": "g", "value": 0.022}, "amount": {"unit": "mol", "value": 0.0015901905481965069}, "equivalent": {"unit": null, "value": 0.13540885967435787}}}, "properties": {"duration": {"unit": "Second(s)", "value": 2}, "temperature": {"unit": "°C", "value": 2}}, "startingMaterials": {"2": {"aux": {"purity": 1, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "H3N", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": 0, "molecularWeight": 17.03052}, "mass": {"unit": "g", "value": 0.2}, "amount": {"unit": "mol", "value": 0.011743622625733096}, "equivalent": {"unit": null, "value": null}}}}], "description": "--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\nops:\\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\n  insert: \\"\\\\n\\"\\n", "observation": "--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\nops:\\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\n  insert: \\"\\\\n\\"\\n", "short_label": "API-R1", "temperature": "{\\"data\\": [], \\"userText\\": \\"\\", \\"valueUnit\\": \\"°C\\"}", "vessel_size": "{\\"unit\\": \\"ml\\", \\"amount\\": null}", "purification": [], "tlc_solvents": "", "rinchi_string": "RInChI=1.00.1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3<>H3N/h1H3<>BH3/h1H3/d-", "rinchi_web_key": "Web-RInChIKey=QIYMARWDEZAJTNBIR-NUHFFFADPSCTJSA", "timestamp_stop": "", "rinchi_long_key": "Long-RInChIKey=SA-BUHFF-QPUYECUOLPXSFR-UHFFFAOYSA-N--QGZKDVFQNNGYKY-UHFFFAOYSA-N--UORVGPXVDQYIDP-UHFFFAOYSA-N", "timestamp_start": "", "tlc_description": "", "rinchi_short_key": "Short-RInChIKey=SA-BUHFF-QPUYECUOLP-QGZKDVFQNN-UORVGPXVDQ-NUHFF-NUHFF-NUHFF-ZZZ", "reaction_svg_file": "ed612b54b097d204efc8df601ea8b808e3741b66b1ca286a3a9f32d781a71685.svg", "dangerous_products": [], "plain_text_description": "", "plain_text_observation": ""}, "v": 1, "ts": 1732083351753}, {"c": {"variations": "[{\\"id\\": 1, \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.0013540885967435786}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 1}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 20}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 1.1743622625733097}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}, {\\"id\\": 2, \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.13540885967435787}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 2}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.2}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.011743622625733096}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}]"}, "v": 2, "ts": 1761303981846}, {"c": {"variations": "[{\\"id\\": 1, \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.0013540885967435786}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 1}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 20}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 1.1743622625733097}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}, {\\"id\\": 2, \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.13540885967435787}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 2}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.2}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.011743622625733096}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}]"}, "m": {}, "v": 3, "ts": 1761303981876}, {"c": {"variations": "{\\"2eaad41c-1bec-480c-89ef-eca2702e4933\\": {\\"id\\": 2, \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.13540885967435787}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 2}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.2}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.011743622625733096}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}, \\"5c7e6ff4-9caa-43e6-9805-af4ebba87e40\\": {\\"id\\": 1, \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.0013540885967435786}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 1}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 20}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 1.1743622625733097}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}}"}, "v": 4, "ts": 1763009596649}, {"c": {"variations": "{\\"2eaad41c-1bec-480c-89ef-eca2702e4933\\": {\\"id\\": 2, \\"uuid\\": \\"2eaad41c-1bec-480c-89ef-eca2702e4933\\", \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.13540885967435787}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 2}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.2}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.011743622625733096}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}, \\"5c7e6ff4-9caa-43e6-9805-af4ebba87e40\\": {\\"id\\": 1, \\"uuid\\": \\"5c7e6ff4-9caa-43e6-9805-af4ebba87e40\\", \\"metadata\\": {\\"notes\\": \\"\\", \\"analyses\\": []}, \\"products\\": {\\"4\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"C11H10\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"products\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 142.19710000000003}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": null}, \\"yield\\": {\\"unit\\": null, \\"value\\": 0}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0}}}, \\"solvents\\": {}, \\"reactants\\": {\\"3\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"BH3\\", \\"coefficient\\": 1, \\"isReference\\": false, \\"materialType\\": \\"reactants\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 13.83482}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 0.022}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 0.0015901905481965069}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": 0.0013540885967435786}}}, \\"properties\\": {\\"duration\\": {\\"unit\\": \\"Second(s)\\", \\"value\\": 2}, \\"temperature\\": {\\"unit\\": \\"°C\\", \\"value\\": 1}}, \\"startingMaterials\\": {\\"2\\": {\\"aux\\": {\\"purity\\": 1, \\"density\\": 0, \\"gasType\\": \\"off\\", \\"loading\\": null, \\"molarity\\": 0, \\"sumFormula\\": \\"H3N\\", \\"coefficient\\": 1, \\"isReference\\": true, \\"materialType\\": \\"startingMaterials\\", \\"vesselVolume\\": 0, \\"molecularWeight\\": 17.03052}, \\"mass\\": {\\"unit\\": \\"g\\", \\"value\\": 20}, \\"amount\\": {\\"unit\\": \\"mol\\", \\"value\\": 1.1743622625733097}, \\"equivalent\\": {\\"unit\\": null, \\"value\\": null}}}}}"}, "v": 5, "ts": 1763009596657}], "v": 5}
2		2025-11-13 04:54:36.226688	2025-11-13 04:55:55.215867	--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\nops:\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\n  insert: "\\n"\n			--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\nops:\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\n  insert: "\\n"\n	{}	{}			0	{"data": [], "userText": "", "valueUnit": "°C"}		779d62b419f418c49538e3c017b2ce65c5898ebff73c1fa1a3cf20d2755c90f9.svg		\N	API-R2	7		{}	RInChI=1.00.1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3<>H3N/h1H3/d+	Long-RInChIKey=SA-FUHFF-QPUYECUOLPXSFR-UHFFFAOYSA-N--QGZKDVFQNNGYKY-UHFFFAOYSA-N	Short-RInChIKey=SA-FUHFF-QPUYECUOLP-QGZKDVFQNN-UHFFFADPSC-NUHFF-NUHFF-NUHFF-ZZZ	Web-RInChIKey=ONFXTVIYXQQOERKPO-NUHFFFADPSCTJSA				{"b3ba05e8-7855-4298-9797-e7cc5f6706a3": {"id": 2, "uuid": "b3ba05e8-7855-4298-9797-e7cc5f6706a3", "metadata": {"notes": "Test 2"}, "products": {}, "solvents": {}, "reactants": {}, "properties": {"duration": {"unit": "Second(s)", "value": 4}}, "startingMaterials": {"5": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": null, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": 5}, "amount": {"unit": "mol", "value": 0.03516246111910861}, "volume": {"unit": "l", "value": 0}, "equivalent": {"unit": null, "value": 1}}}}, "bf7593ac-1b23-47df-b452-75b3f30f1b6a": {"id": 1, "uuid": "bf7593ac-1b23-47df-b452-75b3f30f1b6a", "metadata": {"notes": "Test\\n"}, "products": {}, "solvents": {}, "reactants": {}, "properties": {"duration": {"unit": "Second(s)", "value": 3}}, "startingMaterials": {"5": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": null, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": 4}, "amount": {"unit": "mol", "value": 0.028129968895286888}, "volume": {"unit": "l", "value": 0}, "equivalent": {"unit": null, "value": 1}}}}}			f	{"unit": "ml", "amount": null}	{"h": [{"c": {"id": 2, "name": "", "role": "", "rxno": "", "origin": null, "status": "", "gaseous": false, "solvent": "", "duration": "", "rf_value": "0", "conditions": "", "created_at": "2025-11-13T04:54:36.226688", "created_by": 7, "deleted_at": null, "updated_at": "2025-11-13T04:54:36.226688", "variations": "{}", "description": "--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\nops:\\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\n  insert: \\"\\\\n\\"\\n", "observation": "--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\nops:\\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\\n  insert: \\"\\\\n\\"\\n", "short_label": "API-R2", "temperature": "{\\"data\\": [], \\"userText\\": \\"\\", \\"valueUnit\\": \\"°C\\"}", "vessel_size": "{\\"unit\\": \\"ml\\", \\"amount\\": null}", "purification": [], "tlc_solvents": "", "rinchi_string": "RInChI=1.00.1S//d+", "rinchi_web_key": "Web-RInChIKey=UHFFFADPSCTJAUYIS-NUHFFFADPSCTJSA", "timestamp_stop": "", "rinchi_long_key": "Long-RInChIKey=SA-FUHFF", "timestamp_start": "", "tlc_description": "", "rinchi_short_key": "Short-RInChIKey=SA-FUHFF-UHFFFADPSC-UHFFFADPSC-UHFFFADPSC-NUHFF-NUHFF-NUHFF-ZZZ", "reaction_svg_file": "12754d42c7c347783fa6b27c02608b97cefec1926c7be9ee965492601462b68eafbe5bee1d61a3236a245ddfe14ea3a95a5052ba4bc205f213c5b875450d5b08.svg", "dangerous_products": [], "plain_text_description": null, "plain_text_observation": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676227}, {"c": {"updated_at": "2025-11-13T04:54:36.335017", "reaction_svg_file": "297737d5fc116aa03b734d96c16dc64dd20ced292d141a043f8ce08034d913e8.svg"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 2, "ts": 1763009676335}, {"c": {"updated_at": "2025-11-13T04:54:36.887903", "rinchi_string": "RInChI=1.00.1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3<>H3N/h1H3/d+", "rinchi_web_key": "Web-RInChIKey=ONFXTVIYXQQOERKPO-NUHFFFADPSCTJSA", "rinchi_long_key": "Long-RInChIKey=SA-FUHFF-QPUYECUOLPXSFR-UHFFFAOYSA-N--QGZKDVFQNNGYKY-UHFFFAOYSA-N", "rinchi_short_key": "Short-RInChIKey=SA-FUHFF-QPUYECUOLP-QGZKDVFQNN-UHFFFADPSC-NUHFF-NUHFF-NUHFF-ZZZ", "reaction_svg_file": "779d62b419f418c49538e3c017b2ce65c5898ebff73c1fa1a3cf20d2755c90f9.svg"}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 3, "ts": 1763009676888}, {"c": {"plain_text_description": "", "plain_text_observation": ""}, "v": 4, "ts": 1763009679034}, {"c": {"origin": {}, "updated_at": "2025-11-13T04:55:55.201587", "variations": {"b3ba05e8-7855-4298-9797-e7cc5f6706a3": {"id": 2, "uuid": "b3ba05e8-7855-4298-9797-e7cc5f6706a3", "metadata": {"notes": "Test 2"}, "products": {}, "solvents": {}, "reactants": {}, "properties": {"duration": {"unit": "Second(s)", "value": 4}}, "startingMaterials": {"5": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": null, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": 5}, "amount": {"unit": "mol", "value": 0.03516246111910861}, "volume": {"unit": "l", "value": 0}, "equivalent": {"unit": null, "value": 1}}}}, "bf7593ac-1b23-47df-b452-75b3f30f1b6a": {"id": 1, "uuid": "bf7593ac-1b23-47df-b452-75b3f30f1b6a", "metadata": {"notes": "Test\\n"}, "products": {}, "solvents": {}, "reactants": {}, "properties": {"duration": {"unit": "Second(s)", "value": 3}}, "startingMaterials": {"5": {"aux": {"purity": 1, "density": 0, "gasType": "off", "loading": null, "molarity": 0, "sumFormula": "C11H10", "coefficient": 1, "isReference": true, "materialType": "startingMaterials", "vesselVolume": null, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": 4}, "amount": {"unit": "mol", "value": 0.028129968895286888}, "volume": {"unit": "l", "value": 0}, "equivalent": {"unit": null, "value": 1}}}}}}, "m": {"_r": 7, "uuid": "ffd31cb0-d827-412a-aec9-a3cd099d2db5"}, "v": 5, "ts": 1763009755202}, {"c": {"updated_at": "2025-11-13T04:55:55.215867"}, "m": {"_r": 7, "uuid": "ffd31cb0-d827-412a-aec9-a3cd099d2db5"}, "v": 6, "ts": 1763009755216}], "v": 6}
\.


--
-- Data for Name: reactions_samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reactions_samples (id, reaction_id, sample_id, reference, equivalent, "position", type, deleted_at, waste, coefficient, show_label, gas_type, gas_phase_data, conversion_rate, created_at, updated_at, log_data) FROM stdin;
1	1	2	t	1	0	ReactionsStartingMaterialSample	\N	f	1	f	\N	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}	\N	\N	\N	{"h": [{"c": {"id": 1, "type": "ReactionsStartingMaterialSample", "waste": false, "gas_type": null, "position": 0, "reference": true, "sample_id": 2, "created_at": null, "deleted_at": null, "equivalent": 1, "show_label": false, "updated_at": null, "coefficient": 1, "reaction_id": 1, "gas_phase_data": "{\\"time\\": {\\"unit\\": \\"h\\", \\"value\\": null}, \\"temperature\\": {\\"unit\\": \\"K\\", \\"value\\": null}, \\"turnover_number\\": null, \\"part_per_million\\": null, \\"turnover_frequency\\": {\\"unit\\": \\"TON/h\\", \\"value\\": null}}", "conversion_rate": null}, "v": 1, "ts": 1761303981824}], "v": 1}
3	1	4	f	0	0	ReactionsProductSample	\N	f	1	f	\N	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}	\N	\N	\N	{"h": [{"c": {"id": 3, "type": "ReactionsProductSample", "waste": false, "gas_type": null, "position": 0, "reference": false, "sample_id": 4, "created_at": null, "deleted_at": null, "equivalent": 0, "show_label": false, "updated_at": null, "coefficient": 1, "reaction_id": 1, "gas_phase_data": "{\\"time\\": {\\"unit\\": \\"h\\", \\"value\\": null}, \\"temperature\\": {\\"unit\\": \\"K\\", \\"value\\": null}, \\"turnover_number\\": null, \\"part_per_million\\": null, \\"turnover_frequency\\": {\\"unit\\": \\"TON/h\\", \\"value\\": null}}", "conversion_rate": null}, "v": 1, "ts": 1761303981824}], "v": 1}
2	1	3	f	0	0	ReactionsReactantSample	\N	f	1	f	\N	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}	\N	\N	\N	{"h": [{"c": {"id": 2, "type": "ReactionsReactantSample", "waste": false, "gas_type": null, "position": 0, "reference": false, "sample_id": 3, "created_at": null, "deleted_at": null, "equivalent": 0, "show_label": false, "updated_at": null, "coefficient": 1, "reaction_id": 1, "gas_phase_data": "{\\"time\\": {\\"unit\\": \\"h\\", \\"value\\": null}, \\"temperature\\": {\\"unit\\": \\"K\\", \\"value\\": null}, \\"turnover_number\\": null, \\"part_per_million\\": null, \\"turnover_frequency\\": {\\"unit\\": \\"TON/h\\", \\"value\\": null}}", "conversion_rate": null}, "v": 1, "ts": 1761303981824}], "v": 1}
4	2	5	t	\N	0	ReactionsStartingMaterialSample	\N	f	1	f	0	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}	\N	2025-11-13 04:54:36.715908	2025-11-13 04:54:36.715908	{"h": [{"c": {"id": 4, "type": "ReactionsStartingMaterialSample", "waste": false, "gas_type": 0, "position": 0, "reference": true, "sample_id": 5, "created_at": "2025-11-13T04:54:36.715908", "deleted_at": null, "equivalent": null, "show_label": false, "updated_at": "2025-11-13T04:54:36.715908", "coefficient": 1, "reaction_id": 2, "gas_phase_data": "{\\"time\\": {\\"unit\\": \\"h\\", \\"value\\": null}, \\"temperature\\": {\\"unit\\": \\"K\\", \\"value\\": null}, \\"turnover_number\\": null, \\"part_per_million\\": null, \\"turnover_frequency\\": {\\"unit\\": \\"TON/h\\", \\"value\\": null}}", "conversion_rate": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676716}], "v": 1}
5	2	6	f	0	0	ReactionsProductSample	\N	f	1	f	0	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}	\N	2025-11-13 04:54:36.824977	2025-11-13 04:55:55.354941	{"h": [{"c": {"id": 5, "type": "ReactionsProductSample", "waste": false, "gas_type": 0, "position": 0, "reference": false, "sample_id": 6, "created_at": "2025-11-13T04:54:36.824977", "deleted_at": null, "equivalent": 0, "show_label": false, "updated_at": "2025-11-13T04:54:36.824977", "coefficient": 1, "reaction_id": 2, "gas_phase_data": null, "conversion_rate": null}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676825}, {"c": {"updated_at": "2025-11-13T04:55:55.354941", "gas_phase_data": {"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}}, "m": {"_r": 7, "uuid": "ffd31cb0-d827-412a-aec9-a3cd099d2db5"}, "v": 2, "ts": 1763009755355}], "v": 2}
\.


--
-- Data for Name: report_templates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.report_templates (id, name, report_type, created_at, updated_at, attachment_id) FROM stdin;
2	Supporting Information	supporting_information	2024-01-23 13:44:02.230599	2024-01-23 13:44:02.230599	2
3	Supporting Information - Standard Reaction	supporting_information_std_rxn	2024-01-23 13:44:02.240574	2024-01-23 13:44:02.240574	3
4	Supporting Information - Spectra	spectrum	2024-01-23 13:44:02.249427	2024-01-23 13:44:02.249427	4
5	Supporting Information - Reaction List (.xlsx)	rxn_list_xlsx	2024-01-23 13:44:02.252289	2024-01-23 13:44:02.252289	\N
6	Supporting Information - Reaction List (.csv)	rxn_list_csv	2024-01-23 13:44:02.254793	2024-01-23 13:44:02.254793	\N
7	Supporting Information - Reaction List (.html)	rxn_list_html	2024-01-23 13:44:02.264547	2024-01-23 13:44:02.264547	5
1	Standard	standard	2024-01-23 13:44:02.219814	2024-01-23 13:44:02.308738	6
\.


--
-- Data for Name: reports; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reports (id, author_id, file_name, file_description, configs, sample_settings, reaction_settings, objects, img_format, file_path, generated_at, deleted_at, created_at, updated_at, template, mol_serials, si_reaction_settings, prd_atts, report_templates_id) FROM stdin;
\.


--
-- Data for Name: reports_users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reports_users (id, user_id, report_id, downloaded_at, deleted_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: research_plan_metadata; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plan_metadata (id, research_plan_id, doi, url, landing_page, title, type, publisher, publication_year, dates, created_at, updated_at, deleted_at, data_cite_prefix, data_cite_created_at, data_cite_updated_at, data_cite_version, data_cite_last_response, data_cite_state, data_cite_creator_name, description, creator, affiliation, contributor, language, rights, format, version, geo_location, funding_reference, subject, alternate_identifier, related_identifier, log_data) FROM stdin;
\.


--
-- Data for Name: research_plan_table_schemas; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plan_table_schemas (id, name, value, created_by, deleted_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: research_plans; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plans (id, name, created_by, deleted_at, created_at, updated_at, body, log_data) FROM stdin;
\.


--
-- Data for Name: research_plans_screens; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plans_screens (screen_id, research_plan_id, id, created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: research_plans_wellplates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plans_wellplates (research_plan_id, wellplate_id, id, created_at, updated_at, deleted_at, log_data) FROM stdin;
\.


--
-- Data for Name: residues; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.residues (id, sample_id, residue_type, custom_info, created_at, updated_at, log_data) FROM stdin;
\.


--
-- Data for Name: sample_tasks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sample_tasks (id, result_value, result_unit, description, creator_id, sample_id, created_at, updated_at, required_scan_results) FROM stdin;
\.


--
-- Data for Name: samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.samples (id, name, target_amount_value, target_amount_unit, created_at, updated_at, description, molecule_id, molfile, purity, deprecated_solvent, impurities, location, is_top_secret, ancestry, external_label, created_by, short_label, real_amount_value, real_amount_unit, imported_readout, deleted_at, sample_svg_file, user_id, identifier, density, melting_point, boiling_point, fingerprint_id, xref, molarity_value, molarity_unit, molecule_name_id, molfile_version, stereo, metrics, decoupled, molecular_mass, sum_formula, solvent, dry_solvent, inventory_sample, log_data) FROM stdin;
1	\N	0	g	2024-01-23 15:17:46.412096	2024-01-23 15:17:46.412096		1	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	1				f	\N		2	MSU-1	\N	g	\N	\N	\N	\N	\N	0	(,)	(,)	1	{}	0	M	3	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f	{"h": [{"c": {"id": 1, "name": null, "xref": "{}", "purity": 1, "stereo": "{\\"abs\\": \\"any\\", \\"rel\\": \\"any\\"}", "density": 0, "metrics": "mmm", "molfile": "\\\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44", "solvent": [], "user_id": null, "ancestry": null, "location": "", "decoupled": false, "created_at": "2024-01-23T15:17:46.412096", "created_by": 2, "deleted_at": null, "identifier": null, "impurities": "", "updated_at": "2024-01-23T15:17:46.412096", "description": "", "dry_solvent": false, "molecule_id": 1, "short_label": "MSU-1", "sum_formula": "", "boiling_point": "(,)", "is_top_secret": false, "melting_point": "(,)", "molarity_unit": "M", "external_label": "", "fingerprint_id": 1, "molarity_value": 0, "molecular_mass": 0, "molfile_version": null, "sample_svg_file": null, "imported_readout": null, "inventory_sample": false, "molecule_name_id": 3, "real_amount_unit": "g", "real_amount_value": null, "deprecated_solvent": "", "target_amount_unit": "g", "target_amount_value": 0}, "v": 1, "ts": 1706023066412}], "v": 1}
2	\N	0	g	2024-11-20 06:11:55.311593	2024-11-20 06:11:55.311593		1	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	1				f	\N		7	API-1	\N	g	\N	\N	\N	\N	\N	0	(,)	(,)	1	{}	0	M	2	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f	{"h": [{"c": {"id": 2, "name": null, "xref": "{}", "purity": 1, "stereo": "{\\"abs\\": \\"any\\", \\"rel\\": \\"any\\"}", "density": 0, "metrics": "mmm", "molfile": "\\\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44", "solvent": [], "user_id": null, "ancestry": null, "location": "", "decoupled": false, "created_at": "2024-11-20T06:11:55.311593", "created_by": 7, "deleted_at": null, "identifier": null, "impurities": "", "updated_at": "2024-11-20T06:11:55.311593", "description": "", "dry_solvent": false, "molecule_id": 1, "short_label": "API-1", "sum_formula": "", "boiling_point": "(,)", "is_top_secret": false, "melting_point": "(,)", "molarity_unit": "M", "external_label": "", "fingerprint_id": 1, "molarity_value": 0, "molecular_mass": 0, "molfile_version": null, "sample_svg_file": null, "imported_readout": null, "inventory_sample": false, "molecule_name_id": 2, "real_amount_unit": "g", "real_amount_value": null, "deprecated_solvent": "", "target_amount_unit": "g", "target_amount_value": 0}, "v": 1, "ts": 1732083115312}], "v": 1}
3	\N	0.022	g	2024-11-20 06:12:56.646234	2024-11-20 06:14:26.471014		2	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e303030302042202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	1				f	\N		7	reactant	\N	g	\N	\N	\N	\N	\N	1	(,)	(,)	2	{}	0	M	4	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f	{"h": [{"c": {"id": 3, "name": null, "xref": "{}", "purity": 1, "stereo": "{\\"abs\\": \\"any\\", \\"rel\\": \\"any\\"}", "density": 1, "metrics": "mmm", "molfile": "\\\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e303030302042202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44", "solvent": [], "user_id": null, "ancestry": null, "location": "", "decoupled": false, "created_at": "2024-11-20T06:12:56.646234", "created_by": 7, "deleted_at": null, "identifier": null, "impurities": "", "updated_at": "2024-11-20T06:14:26.471014", "description": "", "dry_solvent": false, "molecule_id": 2, "short_label": "reactant", "sum_formula": "", "boiling_point": "(,)", "is_top_secret": false, "melting_point": "(,)", "molarity_unit": "M", "external_label": "", "fingerprint_id": 2, "molarity_value": 0, "molecular_mass": 0, "molfile_version": null, "sample_svg_file": null, "imported_readout": null, "inventory_sample": false, "molecule_name_id": 4, "real_amount_unit": "g", "real_amount_value": null, "deprecated_solvent": "", "target_amount_unit": "g", "target_amount_value": 0.022}, "v": 1, "ts": 1732083266471}], "v": 1}
4	API-R1-A	0	g	2024-11-20 06:14:15.809067	2024-11-20 06:14:26.498125		3	\\x0a20204b657463686572203131323032343037313432442031202020312e30303030302020202020302e30303030302020202020300a0a2031312031322020302020202020302020302020202020202020202020203939392056323030300a20202020342e363530302020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832312020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d312e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a2020312020322020312020302020202020302020300a2020322020332020312020302020202020302020300a2020332020342020312020302020202020302020300a2020342020352020322020302020202020302020300a2020352020362020312020302020202020302020300a2020362020312020322020302020202020302020300a2020322020372020322020302020202020302020300a2020372020382020312020302020202020302020300a2020382020392020322020302020202020302020300a2020392031302020312020302020202020302020300a2031302020332020322020302020202020302020300a2020312031312020312020302020202020302020300a4d2020454e440a242424240a0a	1				f	\N		7	API-3	\N	g	\N	\N	18bb8133763ad42880d28d267b93f23f6fa48d34516d5c966d8f28c05efe8b8458ebae6f5f1fd5f3581fdab74f1b9b443eb8869ed46b8b067eedae28cfb3245f.svg	\N	\N	0	(,)	(,)	3	{}	0	M	6	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f	{"h": [{"c": {"id": 4, "name": "API-R1-A", "xref": "{}", "purity": 1, "stereo": "{\\"abs\\": \\"any\\", \\"rel\\": \\"any\\"}", "density": 0, "metrics": "mmm", "molfile": "\\\\x0a20204b657463686572203131323032343037313432442031202020312e30303030302020202020302e30303030302020202020300a0a2031312031322020302020202020302020302020202020202020202020203939392056323030300a20202020342e363530302020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832312020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d312e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a2020312020322020312020302020202020302020300a2020322020332020312020302020202020302020300a2020332020342020312020302020202020302020300a2020342020352020322020302020202020302020300a2020352020362020312020302020202020302020300a2020362020312020322020302020202020302020300a2020322020372020322020302020202020302020300a2020372020382020312020302020202020302020300a2020382020392020322020302020202020302020300a2020392031302020312020302020202020302020300a2031302020332020322020302020202020302020300a2020312031312020312020302020202020302020300a4d2020454e440a242424240a0a", "solvent": [], "user_id": null, "ancestry": null, "location": "", "decoupled": false, "created_at": "2024-11-20T06:14:15.809067", "created_by": 7, "deleted_at": null, "identifier": null, "impurities": "", "updated_at": "2024-11-20T06:14:26.498125", "description": "", "dry_solvent": false, "molecule_id": 3, "short_label": "API-3", "sum_formula": "", "boiling_point": "(,)", "is_top_secret": false, "melting_point": "(,)", "molarity_unit": "M", "external_label": "", "fingerprint_id": 3, "molarity_value": 0, "molecular_mass": 0, "molfile_version": null, "sample_svg_file": "18bb8133763ad42880d28d267b93f23f6fa48d34516d5c966d8f28c05efe8b8458ebae6f5f1fd5f3581fdab74f1b9b443eb8869ed46b8b067eedae28cfb3245f.svg", "imported_readout": null, "inventory_sample": false, "molecule_name_id": 6, "real_amount_unit": "g", "real_amount_value": null, "deprecated_solvent": "", "target_amount_unit": "g", "target_amount_value": 0}, "v": 1, "ts": 1732083266498}], "v": 1}
5	API-R1-A	0	g	2025-11-13 04:54:36.591863	2025-11-13 04:54:36.591863		3	\\x0a20204b657463686572203131323032343037313432442031202020312e30303030302020202020302e30303030302020202020300a0a2031312031322020302020202020302020302020202020202020202020203939392056323030300a20202020342e363530302020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832312020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d312e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a2020312020322020312020302020202020302020300a2020322020332020312020302020202020302020300a2020332020342020312020302020202020302020300a2020342020352020322020302020202020302020300a2020352020362020312020302020202020302020300a2020362020312020322020302020202020302020300a2020322020372020322020302020202020302020300a2020372020382020312020302020202020302020300a2020382020392020322020302020202020302020300a2020392031302020312020302020202020302020300a2031302020332020322020302020202020302020300a2020312031312020312020302020202020302020300a4d2020454e440a242424240a0a	1				f	4		7	API-3-1	\N	g	\N	\N	18bb8133763ad42880d28d267b93f23f6fa48d34516d5c966d8f28c05efe8b8458ebae6f5f1fd5f3581fdab74f1b9b443eb8869ed46b8b067eedae28cfb3245f.svg	\N	\N	0	(,)	(,)	3	{"inventory_label": null}	0	M	6	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f	{"h": [{"c": {"id": 5, "name": "API-R1-A", "xref": "{\\"inventory_label\\": null}", "purity": 1, "stereo": "{\\"abs\\": \\"any\\", \\"rel\\": \\"any\\"}", "density": 0, "metrics": "mmm", "molfile": "\\\\x0a20204b657463686572203131323032343037313432442031202020312e30303030302020202020302e30303030302020202020300a0a2031312031322020302020202020302020302020202020202020202020203939392056323030300a20202020342e363530302020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832312020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d312e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a2020312020322020312020302020202020302020300a2020322020332020312020302020202020302020300a2020332020342020312020302020202020302020300a2020342020352020322020302020202020302020300a2020352020362020312020302020202020302020300a2020362020312020322020302020202020302020300a2020322020372020322020302020202020302020300a2020372020382020312020302020202020302020300a2020382020392020322020302020202020302020300a2020392031302020312020302020202020302020300a2031302020332020322020302020202020302020300a2020312031312020312020302020202020302020300a4d2020454e440a242424240a0a", "solvent": [], "user_id": null, "ancestry": "4", "location": "", "decoupled": false, "created_at": "2025-11-13T04:54:36.591863", "created_by": 7, "deleted_at": null, "identifier": null, "impurities": "", "updated_at": "2025-11-13T04:54:36.591863", "description": "", "dry_solvent": false, "molecule_id": 3, "short_label": "API-3-1", "sum_formula": "", "boiling_point": "(,)", "is_top_secret": false, "melting_point": "(,)", "molarity_unit": "M", "external_label": "", "fingerprint_id": 3, "molarity_value": 0, "molecular_mass": 0, "molfile_version": null, "sample_svg_file": "18bb8133763ad42880d28d267b93f23f6fa48d34516d5c966d8f28c05efe8b8458ebae6f5f1fd5f3581fdab74f1b9b443eb8869ed46b8b067eedae28cfb3245f.svg", "imported_readout": null, "inventory_sample": false, "molecule_name_id": 6, "real_amount_unit": "g", "real_amount_value": null, "deprecated_solvent": "", "target_amount_unit": "g", "target_amount_value": 0}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676592}], "v": 1}
6	API-R2-A	0	g	2025-11-13 04:54:36.786793	2025-11-13 04:54:36.786793		1	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	1				f	\N		7	API-4	\N	g		\N	\N	\N	\N	0	(,)	(,)	1	{}	0	M	2	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f	{"h": [{"c": {"id": 6, "name": "API-R2-A", "xref": "{}", "purity": 1, "stereo": "{\\"abs\\": \\"any\\", \\"rel\\": \\"any\\"}", "density": 0, "metrics": "mmm", "molfile": "\\\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44", "solvent": [], "user_id": null, "ancestry": null, "location": "", "decoupled": false, "created_at": "2025-11-13T04:54:36.786793", "created_by": 7, "deleted_at": null, "identifier": null, "impurities": "", "updated_at": "2025-11-13T04:54:36.786793", "description": "", "dry_solvent": false, "molecule_id": 1, "short_label": "API-4", "sum_formula": "", "boiling_point": "(,)", "is_top_secret": false, "melting_point": "(,)", "molarity_unit": "M", "external_label": "", "fingerprint_id": 1, "molarity_value": 0, "molecular_mass": 0, "molfile_version": null, "sample_svg_file": null, "imported_readout": "", "inventory_sample": false, "molecule_name_id": 2, "real_amount_unit": "g", "real_amount_value": null, "deprecated_solvent": "", "target_amount_unit": "g", "target_amount_value": 0}, "m": {"_r": 7, "uuid": "46077e12-4ee4-4109-8ede-93513188ba17"}, "v": 1, "ts": 1763009676787}], "v": 1}
\.


--
-- Data for Name: scan_results; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.scan_results (id, measurement_value, measurement_unit, title, "position", sample_task_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.schema_migrations (version) FROM stdin;
20150618114948
20150728120436
20150817085601
20150817200859
20150818100730
20150825144929
20150828072626
20150831071333
20150916161541
20150917124536
20150918115918
20150928075813
20150928130831
20150929123358
20151002083208
20151004084416
20151005145922
20151005151021
20151005195648
20151006123344
20151007231740
20151009130555
20151009135514
20151012083428
20151012130019
20151015161007
20151021100740
20151023135011
20151027111518
20151027164552
20151109131413
20151111140555
20151118090203
20151127145354
20151203092316
20151204112634
20151207170817
20160126113426
20160316083518
20160404115858
20160411112619
20160413144919
20160414070925
20160428115515
20160429072510
20160518121815
20160524102833
20160623081843
20160627102544
20160627110544
20160627115254
20160630100818
20160715160520
20160718071541
20160719113538
20160719130259
20160719152553
20160720092012
20160720111523
20160725120549
20160725135743
20160725142712
20160726162453
20160727160203
20160729105554
20160809122557
20160815080243
20160822115224
20160823110331
20160825120422
20160901142139
20160920091519
20160920105050
20160926113940
20161004121244
20161024083139
20161109141353
20161201152821
20161207084424
20161212154142
20161214131916
20161215133014
20161221125649
20161221130945
20161221143217
20170103155405
20170103155423
20170104085233
20170105094838
20170111100223
20170113154425
20170123094157
20170125112946
20170201113437
20170201123538
20170202075710
20170202080000
20170209094545
20170210102655
20170215133510
20170221164718
20170307101429
20170320084528
20170322135348
20170327091111
20170329121122
20170329121123
20170331121124
20170405152400
20170405152500
20170405152501
20170411104507
20170414012345
20170509084420
20170509085000
20170512110856
20170524130531
20170620133722
20170629121125
20170705081238
20170801141124
20170802080219
20170809123558
20170816134224
20170816135217
20170821154142
20170828104739
20170901112025
20170905071218
20170906105933
20170908105401
20170914092558
20170914130439
20170928075547
20170928124229
20171004132647
20171014184604
20171019102800
20171121171212
20171220140635
20180115110710
20180205132254
20180226130228
20180226130229
20180312095413
20180510101010
20180516151737
20180518053658
20180524103806
20180529123358
20180618052835
20180620144623
20180620144710
20180704131215
20180709180000
20180723124200
20180723140300
20180726152200
20180801110000
20180801120000
20180801130000
20180802164000
20180802170000
20180807153900
20180812115719
20180814131055
20180814141400
20180815144035
20180816161600
20180827140000
20180831084640
20180831125901
20180903134741
20180918085000
20180918120000
20180921140800
20180925165000
20181009155001
20181029081414
20181105103800
20181122140000
20181122145822
20181128110000
20181206075723
20181207091112
20181207100526
20190110083400
20190204152500
20190206100500
20190307113259
20190320145415
20190508084000
20190514080856
20190604100811
20190617144801
20190617153000
20190618153000
20190619135600
20190619153000
20190708112047
20190712090136
20190716092051
20190722090944
20190724100000
20190731120000
20190812124349
20190828111502
20191128100001
20200117115709
20200212100002
20200306100001
20200513100000
20200702091855
20200710114058
20200715094007
20200819093220
20200819131000
20200820102805
20200820160020
20200824143243
20200824143253
20200824153242
20200827133000
20200827144816
20200911075633
20200917155839
20200928115156
20201023170550
20201027130000
20201109012155
20201123234035
20201126081805
20201127071139
20201130121311
20201201051854
20201209222212
20201214090807
20201216153122
20201217172428
20210108230206
20210216132619
20210217164124
20210222154608
20210225075410
20210303140000
20210312160000
20210316132500
20210316132800
20210316133000
20210318133000
20210331221122
20210413163755
20210416075103
20210429141415
20210507131044
20210511132059
20210527172347
20210604232803
20210605105020
20210605125007
20210610000001
20210610105014
20210614115000
20210617132532
20210621145002
20210621155000
20210714082826
20210727145003
20210816094212
20210816113952
20210820165003
20210825082859
20210916091017
20210920171211
20210921114428
20210923131838
20210924095106
20211105091019
20211105111420
20211111112219
20211115222715
20211116000000
20211117000000
20211117235010
20211118112711
20211122142906
20211206144812
20220114085300
20220116164546
20220123122040
20220127000608
20220214100000
20220217161840
20220309182512
20220317004217
20220406094235
20220408113102
20220707164502
20220712100010
20220816070825
20220908132540
20220926103002
20221024150829
20221104155451
20221123090544
20221128073938
20221202150826
20230105122756
20230112090901
20230124152436
20230125152149
20230210124435
20230306114227
20230320132646
20230323115540
20230420121233
20230426124600
20230503090936
20230522075503
20230531142756
20230613063121
20230630123412
20230630125148
20230630140647
20230714100005
20230804100000
20230810100000
20230814110512
20230814121455
20230925101807
20231106000000
20231218191658
20231218191929
20230927073354
20230927073410
20230927073435
20231219151632
20231219152154
20231219162631
20240129134421
20240320122428
20240229000000
20240328150631
20240424120634
20230213102539
20230323160712
20231219141841
20231219171103
20240115161400
20240115163018
20240126000000
20240205131406
20240425095433
20240530000001
20240610144934
20240625105013
20240709095242
20240709095243
20240711120833
20240726064022
20190305134152
20230120134152
20240206164554
20240206171038
20240207121720
20240207123444
20240319000000
20240425110005
20240531112321
20240626081233
20240710102258
20240712151806
20240718021724
20240808125800
20240808125801
20240808125802
20240917085816
20241104100001
20241129093956
20250101000000
20250218160000
20250218161000
20250218161800
20250226095051
20250304140809
20250306110000
20250306120000
20250326151800
20250328123030
20250422105404
20250422115436
20250506133809
20250324135000
20250515141514
20250526160014
20250701134000
20251007100040
\.


--
-- Data for Name: scifinder_n_credentials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.scifinder_n_credentials (id, access_token, refresh_token, expires_at, created_by, updated_at) FROM stdin;
\.


--
-- Data for Name: screens; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.screens (id, description, name, result, collaborator, conditions, requirements, created_at, updated_at, deleted_at, component_graph_data, plain_text_description, log_data) FROM stdin;
\.


--
-- Data for Name: screens_wellplates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.screens_wellplates (id, screen_id, wellplate_id, deleted_at) FROM stdin;
\.


--
-- Data for Name: segment_klasses; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.segment_klasses (id, element_klass_id, label, "desc", properties_template, is_active, place, created_by, created_at, updated_at, deleted_at, uuid, properties_release, released_at, identifier, sync_time, updated_by, released_by, sync_by, admin_ids, user_ids, version) FROM stdin;
2	2	ApiTester	For api testing	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "4026724d-e042-4da4-ad7d-f149343857a8", "klass": "SegmentKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "One", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Text", "label": "Text", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	t	100	7	2024-02-16 09:49:33.570494	2024-02-16 09:50:15.230883	\N	4026724d-e042-4da4-ad7d-f149343857a8	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "4026724d-e042-4da4-ad7d-f149343857a8", "klass": "SegmentKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "One", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Text", "label": "Text", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	2024-02-16 09:50:15.227031	\N	\N	7	7	\N	{}	{}	1.0
1	7	TrySeg1		{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "305cfc10-6497-42c3-9395-fc662ebf7b8f", "klass": "SegmentKlass", "layers": {"main": {"wf": false, "key": "main", "cols": 1, "color": "none", "label": "Main Layer", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	t	100	2	2024-01-25 09:22:58.44907	2024-12-04 12:57:28.685524	2024-12-04 12:57:28.685518	305cfc10-6497-42c3-9395-fc662ebf7b8f	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "305cfc10-6497-42c3-9395-fc662ebf7b8f", "klass": "SegmentKlass", "layers": {"main": {"wf": false, "key": "main", "cols": 1, "color": "none", "label": "Main Layer", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	2024-01-25 09:23:27.596462	\N	\N	2	2	\N	{}	{}	1.0
\.


--
-- Data for Name: segment_klasses_revisions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.segment_klasses_revisions (id, segment_klass_id, uuid, properties_release, released_at, released_by, created_by, created_at, updated_at, deleted_at, version) FROM stdin;
3	2	957d32c7-2b14-4bef-b0cb-95ecf84ff469	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "labimotion": "1.1.3"}, "uuid": "957d32c7-2b14-4bef-b0cb-95ecf84ff469", "klass": "SegmentKlass", "layers": {}, "select_options": {}}	2024-02-16 09:49:33.583032	7	\N	2024-02-16 09:49:33.603906	2024-02-16 09:49:33.603906	\N	\N
4	2	4026724d-e042-4da4-ad7d-f149343857a8	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.3"}, "uuid": "4026724d-e042-4da4-ad7d-f149343857a8", "klass": "SegmentKlass", "layers": {"one": {"wf": false, "key": "one", "cols": 1, "color": "none", "label": "One", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Text", "label": "Text", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	2024-02-16 09:50:15.227031	7	\N	2024-02-16 09:50:15.237188	2024-02-16 09:50:15.237188	\N	1.0
1	1	f79898fc-2c25-4424-a6c7-8d45da1e745d	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "labimotion": "1.1.1"}, "uuid": "f79898fc-2c25-4424-a6c7-8d45da1e745d", "klass": "SegmentKlass", "layers": {}, "select_options": {}}	2024-01-25 09:22:58.464231	2	\N	2024-01-25 09:22:58.515586	2024-12-04 12:57:28.684727	2024-12-04 12:57:28.684721	\N
2	1	305cfc10-6497-42c3-9395-fc662ebf7b8f	{"pkg": {"eln": {"version": "1.8.0", "base_revision": "7bd6a5d81", "current_revision": 0}, "name": "chem-generic-ui", "version": "1.0.11", "labimotion": "1.1.1"}, "uuid": "305cfc10-6497-42c3-9395-fc662ebf7b8f", "klass": "SegmentKlass", "layers": {"main": {"wf": false, "key": "main", "cols": 1, "color": "none", "label": "Main Layer", "style": "panel_generic_heading", "fields": [{"type": "text", "field": "Name", "label": "Name", "default": "", "position": 1, "sub_fields": [], "text_sub_fields": []}], "position": 10, "timeRecord": "", "wf_position": 0}}, "version": "1.0", "identifier": null, "select_options": {}}	2024-01-25 09:23:27.596462	2	\N	2024-01-25 09:23:27.617482	2024-12-04 12:57:28.685147	2024-12-04 12:57:28.685142	1.0
\.


--
-- Data for Name: segments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.segments (id, segment_klass_id, element_type, element_id, properties, created_by, created_at, updated_at, deleted_at, uuid, klass_uuid, properties_release) FROM stdin;
\.


--
-- Data for Name: segments_revisions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.segments_revisions (id, segment_id, uuid, klass_uuid, properties, created_by, created_at, updated_at, deleted_at, properties_release) FROM stdin;
\.


--
-- Data for Name: subscriptions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.subscriptions (id, channel_id, user_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: sync_collections_users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sync_collections_users (id, user_id, collection_id, shared_by_id, permission_level, sample_detail_level, reaction_detail_level, wellplate_detail_level, screen_detail_level, fake_ancestry, researchplan_detail_level, label, created_at, updated_at, element_detail_level, celllinesample_detail_level, devicedescription_detail_level) FROM stdin;
\.


--
-- Data for Name: text_templates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.text_templates (id, type, user_id, name, data, deleted_at, created_at, updated_at) FROM stdin;
1	PredefinedTextTemplate	1	ndash	{"ops": [{"insert": "–"}], "icon": "fa fa-minus"}	\N	2024-01-23 13:44:01.107284	2024-01-23 13:44:01.107284
2	PredefinedTextTemplate	1	water-free	{"ops": [{"insert": "The reaction has been conducted in dry glass ware under inert atmosphere."}], "icon": "icon-water-free"}	\N	2024-01-23 13:44:01.112592	2024-01-23 13:44:01.112592
3	PredefinedTextTemplate	1	resin-solvent	{"ops": [{"insert": "The resin (xxx mg, loading = X.XX g/mol, XX.X mmol) was swollen in xx mL of SOLVENT for xx min at room temperature."}], "icon": "icon-resin-solvent"}	\N	2024-01-23 13:44:01.11685	2024-01-23 13:44:01.11685
4	PredefinedTextTemplate	1	resin-solvent-reagent	{"ops": [{"insert": "The resin (xxx mg, loading = X.XX g/mol, XX.X mmol) was filled into a 10 mL crimp cap vial and was swollen in xx mL of SOLVENT. After xx min, xxx.x mg of REAGENT (XX.X mmol, XX.X equiv.) and XX.X mg of REAGENT (XX.X mg, XX.X mmol, X.XX equiv.) were added. The reaction mixture was shaken at XX °C for XX h."}], "icon": "icon-resin-solvent-reagent"}	\N	2024-01-23 13:44:01.121268	2024-01-23 13:44:01.121268
5	PredefinedTextTemplate	1	hand-stop	{"ops": [{"insert": "After complete conversion of the starting material, the reaction was quenched "}, {"insert": "via", "attributes": {"italic": true}}, {"insert": " careful addition of saturated NaHCO"}, {"insert": "3", "attributes": {"script": "sub"}}, {"insert": "-solution."}], "icon": "icon-hand-stop"}	\N	2024-01-23 13:44:01.125653	2024-01-23 13:44:01.125653
6	PredefinedTextTemplate	1	reaction-procedure	{"ops": [{"insert": "The reaction mixture was poured into a glass funnel with filter paper and the polymer beads were washed XX times according to the following procedure: (1) SOLVENT [x repetitions] (2)  SOLVENT [x repetitions] (3)  SOLVENT [x repetitions] (4)  SOLVENT [x repetitions] (5)  SOLVENT [x repetitions]."}], "icon": "icon-reaction-procedure"}	\N	2024-01-23 13:44:01.129932	2024-01-23 13:44:01.129932
7	PredefinedTextTemplate	1	gpx-a	{"ops": [{"insert": "According to GPX, AMOUNT g (XXX mmol, XX equiv.) of STARTING MATERIAL were reacted with XX.X mL (XX.X mg, XX.X mmol, X.XX equiv.) of REAGENT und X.XX mg (24.0 mmol, 5.00 equiv.) of REAGENT in XX mL of SOLVENT at XX °C for XX h."}], "icon": "icon-gpx-a"}	\N	2024-01-23 13:44:01.134213	2024-01-23 13:44:01.134213
8	PredefinedTextTemplate	1	gpx-b	{"ops": [{"insert": "According to GPX, AMOUNT g (XXX mmol, XX equiv.) of STARTING MATERIAL were reacted with XX.X mL (XX.X mg, XX.X mmol, X.XX equiv.) of REAGENT und X.XX mg (24.0 mmol, 5.00 equiv.) of REAGENT in XX mL of SOLVENT at XX °C for XX h."}], "icon": "icon-gpx-b"}	\N	2024-01-23 13:44:01.138334	2024-01-23 13:44:01.138334
9	PredefinedTextTemplate	1	washed-nahco3	{"ops": [{"insert": "The reaction mixture was poured into a separation funnel and the organic layer was washed successively with xx mL of NaHCO"}, {"insert": "3", "attributes": {"script": "sub"}}, {"insert": "-solution, xx mL of brine and xx mL of water. The aqueous layers were recombined and reextracted with ethyl acetate.\\nThe organic layers were collected and were dried by the addition of Na"}, {"insert": "2", "attributes": {"script": "sub"}}, {"insert": "SO"}, {"insert": "4", "attributes": {"script": "sub"}}, {"insert": "/MgSO"}, {"insert": "4", "attributes": {"script": "sub"}}, {"insert": ". The mixture was filtered through a glass funnel and the solvent was evaporated under reduced pressure."}], "icon": "icon-washed-nahco3"}	\N	2024-01-23 13:44:01.142879	2024-01-23 13:44:01.142879
10	PredefinedTextTemplate	1	acidified-hcl	{"ops": [{"insert": "The reaction mixture was poured into a separation funnel and was acidified by the addition of 1 M HCl. The aqueous layer was collected and adjusted to pH 8-9 by addition of saturated NaHCO"}, {"insert": "3", "attributes": {"script": "sub"}}, {"insert": "-solution. xx mL of SOLVENT were added and the aqueous phase was extracted three times. After washing with brine and water, the organic layers were collected and were dried by the addition of Na"}, {"insert": "2", "attributes": {"script": "sub"}}, {"insert": "SO"}, {"insert": "4", "attributes": {"script": "sub"}}, {"insert": "/MgSO"}, {"insert": "4", "attributes": {"script": "sub"}}, {"insert": ". The mixture was filtered through a glass funnel and the solvent was evaporated under reduced pressure."}], "icon": "icon-acidified-hcl"}	\N	2024-01-23 13:44:01.14738	2024-01-23 13:44:01.14738
11	PredefinedTextTemplate	1	tlc-control	{"ops": [{"insert": "The progress of the reaction was observed via TLC control (cyclohexane:ethyl acetate; xx:xx; R"}, {"insert": "f = ", "attributes": {"italic": true, "script": "sub"}}, {"insert": "0.XX)."}], "icon": "icon-tlc-control"}	\N	2024-01-23 13:44:01.151973	2024-01-23 13:44:01.151973
12	PredefinedTextTemplate	1	dried	{"ops": [{"insert": "The combined organic layers were dried by the addition of Na"}, {"insert": "2", "attributes": {"script": "sub"}}, {"insert": "SO"}, {"insert": "4", "attributes": {"script": "sub"}}, {"insert": "/MgSO"}, {"insert": "4", "attributes": {"script": "sub"}}, {"insert": ". The mixture was filtered through a glass funnel and the solvent was evaporated under reduced pressure."}], "icon": "icon-dried"}	\N	2024-01-23 13:44:01.157022	2024-01-23 13:44:01.157022
13	PredefinedTextTemplate	1	isolated	{"ops": [{"insert": "The target compound was isolated by filtering of the resulting mixture through a glass funnel and was washed AMOUNT times with SOLVENT."}], "icon": "icon-isolated"}	\N	2024-01-23 13:44:01.161436	2024-01-23 13:44:01.161436
14	PredefinedTextTemplate	1	residue-purified	{"ops": [{"insert": "The crude residue was purified "}, {"insert": "via", "attributes": {"italic": true}}, {"insert": " column chromatography (cyclohexane:ethyl acetate; xx:xx → cyclohexane:ethyl acetate; xx:xx). The target compound was isolated as a colorless solid in xx% yield (xx mg, xx mmol). R"}, {"insert": "f = ", "attributes": {"italic": true, "script": "sub"}}, {"insert": "0.XX (cyclohexane:ethyl acetate)."}], "icon": "icon-residue-purified"}	\N	2024-01-23 13:44:01.165745	2024-01-23 13:44:01.165745
15	PredefinedTextTemplate	1	residue-adsorbed	{"ops": [{"insert": "The crude residue was adsorbed on a small amount of silica gel/Celite and was purified "}, {"insert": "via", "attributes": {"italic": true}}, {"insert": " column chromatography (cyclohexane:ethyl acetate; xx:xx → cyclohexane:ethyl acetate; xx:xx). The target compound was isolated as a colorless solid in xx% yield (xx mg, xx mmol). R"}, {"insert": "f = ", "attributes": {"italic": true, "script": "sub"}}, {"insert": "0.XX (cyclohexane:ethyl acetate)."}], "icon": "icon-residue-adsorbed"}	\N	2024-01-23 13:44:01.170337	2024-01-23 13:44:01.170337
16	PredefinedTextTemplate	1	residue-dissolved	{"ops": [{"insert": "The crude residue was dissolved in a small amount of SOLVENT and was purified "}, {"insert": "via", "attributes": {"italic": true}}, {"insert": " column chromatography (cyclohexane:ethyl acetate; xx:xx → cyclohexane:ethyl acetate; xx:xx). The target compound was isolated as a colorless STATE in xx% yield (xx mg, xx mmol). R"}, {"insert": "f = ", "attributes": {"italic": true, "script": "sub"}}, {"insert": "0.XX (cyclohexane:ethyl acetate)."}], "icon": "icon-residue-dissolved"}	\N	2024-01-23 13:44:01.17503	2024-01-23 13:44:01.17503
17	PredefinedTextTemplate	1	h-nmr	{"ops": [{"insert": "1", "attributes": {"script": "super"}}, {"insert": "H NMR (ppm) δ = "}], "text": "H"}	\N	2024-01-23 13:44:01.179245	2024-01-23 13:44:01.179245
18	PredefinedTextTemplate	1	c-nmr	{"ops": [{"insert": "13", "attributes": {"script": "super"}}, {"insert": "C NMR (ppm) δ = "}], "text": "C"}	\N	2024-01-23 13:44:01.183537	2024-01-23 13:44:01.183537
19	PredefinedTextTemplate	1	ir	{"ops": [{"insert": "IR (ATR, ṽ) = "}, {"insert": " cm"}, {"insert": "–1", "attributes": {"script": "super"}}, {"insert": ". "}]}	\N	2024-01-23 13:44:01.187907	2024-01-23 13:44:01.187907
20	PredefinedTextTemplate	1	uv	{"ops": [{"insert": "UV-VIS (CH"}, {"insert": "2", "attributes": {"script": "sub"}}, {"insert": "Cl"}, {"insert": "2", "attributes": {"script": "sub"}}, {"insert": "), λ"}, {"insert": "max", "attributes": {"script": "sub"}}, {"insert": "(log ε) = ."}]}	\N	2024-01-23 13:44:01.193044	2024-01-23 13:44:01.193044
21	PredefinedTextTemplate	1	ea	{"ops": [{"insert": "EA (): Calcd C ; H ; N ; O . Found C ; H ; N ; O ."}]}	\N	2024-01-23 13:44:01.197332	2024-01-23 13:44:01.197332
22	PredefinedTextTemplate	1	ei	{"ops": [{"insert": "MS (EI, 70 eV, XX °C), m/z (%):"}]}	\N	2024-01-23 13:44:01.201423	2024-01-23 13:44:01.201423
23	PredefinedTextTemplate	1	fab	{"ops": [{"insert": "MS (FAB, 3-NBA), m/z (%):"}]}	\N	2024-01-23 13:44:01.20543	2024-01-23 13:44:01.20543
24	PredefinedTextTemplate	1	esi	{"ops": [{"insert": "MS (ESI), m/z (%):"}]}	\N	2024-01-23 13:44:01.209575	2024-01-23 13:44:01.209575
25	PredefinedTextTemplate	1	apci	{"ops": [{"insert": "MS (APCI, CH"}, {"insert": "3", "attributes": {"script": "sub"}}, {"insert": "COONH"}, {"insert": "4", "attributes": {"script": "sub"}}, {"insert": "), m/z (%): "}]}	\N	2024-01-23 13:44:01.213555	2024-01-23 13:44:01.213555
26	PredefinedTextTemplate	1	asap	{"ops": [{"insert": "MS (ASAP), m/z (%):"}]}	\N	2024-01-23 13:44:01.217793	2024-01-23 13:44:01.217793
27	PredefinedTextTemplate	1	maldi	{"ops": [{"insert": "MS (MALDI-TOF), m/z (%):"}]}	\N	2024-01-23 13:44:01.221846	2024-01-23 13:44:01.221846
28	PredefinedTextTemplate	1	m+	{"ops": [{"insert": "[M]"}, {"insert": "+", "attributes": {"script": "super"}}]}	\N	2024-01-23 13:44:01.225978	2024-01-23 13:44:01.225978
29	PredefinedTextTemplate	1	hr	{"ops": [{"insert": "HRMS (): calcd , found ."}]}	\N	2024-01-23 13:44:01.230128	2024-01-23 13:44:01.230128
30	PredefinedTextTemplate	1	hr-ei	{"ops": [{"insert": "HRMS–EI "}, {"insert": "(m/z)", "attributes": {"italic": true}}, {"insert": ": [M]"}, {"insert": "+", "attributes": {"script": "super"}}, {"insert": " calcd for "}, {"insert": "MASS", "attributes": {"bold": true}}, {"insert": "; found "}, {"insert": "MASS", "attributes": {"bold": true}}, {"insert": "."}]}	\N	2024-01-23 13:44:01.241062	2024-01-23 13:44:01.241062
31	PredefinedTextTemplate	1	hr-fab	{"ops": [{"insert": "HRMS–FAB "}, {"insert": "(m/z)", "attributes": {"italic": true}}, {"insert": ": [M + H]"}, {"insert": "+", "attributes": {"script": "super"}}, {"insert": " calcd for "}, {"insert": "MASS", "attributes": {"bold": true}}, {"insert": "; found "}, {"insert": "MASS", "attributes": {"bold": true}}, {"insert": "."}]}	\N	2024-01-23 13:44:01.245834	2024-01-23 13:44:01.245834
32	SampleTextTemplate	2	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:02.29603	2024-01-23 15:12:02.29603
33	ReactionTextTemplate	2	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:02.306072	2024-01-23 15:12:02.306072
34	WellplateTextTemplate	2	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:02.316562	2024-01-23 15:12:02.316562
35	ScreenTextTemplate	2	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:02.339075	2024-01-23 15:12:02.339075
36	ResearchPlanTextTemplate	2	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:02.351603	2024-01-23 15:12:02.351603
37	ReactionDescriptionTextTemplate	2	\N	{"_toolbar": ["acidified-hcl", "dried", "gpx-a", "gpx-b", "hand-stop", "isolated", "ndash", "reaction-procedure", "residue-adsorbed", "residue-dissolved", "residue-purified", "resin-solvent", "resin-solvent-reagent", "tlc-control", "washed-nahco3", "water-free"]}	\N	2024-01-23 15:12:02.361915	2024-01-23 15:12:02.361915
38	ElementTextTemplate	2	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:02.373129	2024-01-23 15:12:02.373129
39	SampleTextTemplate	3	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:19.932453	2024-01-23 15:12:19.932453
40	ReactionTextTemplate	3	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:19.939297	2024-01-23 15:12:19.939297
41	WellplateTextTemplate	3	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:19.946314	2024-01-23 15:12:19.946314
42	ScreenTextTemplate	3	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:19.953452	2024-01-23 15:12:19.953452
43	ResearchPlanTextTemplate	3	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:19.961094	2024-01-23 15:12:19.961094
44	ReactionDescriptionTextTemplate	3	\N	{"_toolbar": ["acidified-hcl", "dried", "gpx-a", "gpx-b", "hand-stop", "isolated", "ndash", "reaction-procedure", "residue-adsorbed", "residue-dissolved", "residue-purified", "resin-solvent", "resin-solvent-reagent", "tlc-control", "washed-nahco3", "water-free"]}	\N	2024-01-23 15:12:19.967103	2024-01-23 15:12:19.967103
45	ElementTextTemplate	3	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-23 15:12:19.974453	2024-01-23 15:12:19.974453
46	SampleTextTemplate	4	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-24 07:01:45.798509	2024-01-24 07:01:45.798509
47	ReactionTextTemplate	4	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-24 07:01:45.810352	2024-01-24 07:01:45.810352
48	WellplateTextTemplate	4	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-24 07:01:45.820198	2024-01-24 07:01:45.820198
49	ScreenTextTemplate	4	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-24 07:01:45.829865	2024-01-24 07:01:45.829865
50	ResearchPlanTextTemplate	4	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-24 07:01:45.83926	2024-01-24 07:01:45.83926
51	ReactionDescriptionTextTemplate	4	\N	{"_toolbar": ["acidified-hcl", "dried", "gpx-a", "gpx-b", "hand-stop", "isolated", "ndash", "reaction-procedure", "residue-adsorbed", "residue-dissolved", "residue-purified", "resin-solvent", "resin-solvent-reagent", "tlc-control", "washed-nahco3", "water-free"]}	\N	2024-01-24 07:01:45.847599	2024-01-24 07:01:45.847599
52	ElementTextTemplate	4	\N	{"MS": ["apci", "asap", "ei", "esi", "fab", "hr", "hr-ei", "hr-fab", "m+", "maldi"], "_toolbar": ["c-nmr", "ea", "h-nmr", "ir", "ndash", "uv"]}	\N	2024-01-24 07:01:45.85758	2024-01-24 07:01:45.85758
53	SampleTextTemplate	5	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:50:38.523588	2024-02-16 08:50:38.523588
54	ReactionTextTemplate	5	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:50:38.534297	2024-02-16 08:50:38.534297
55	WellplateTextTemplate	5	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:50:38.54511	2024-02-16 08:50:38.54511
56	ScreenTextTemplate	5	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:50:38.55481	2024-02-16 08:50:38.55481
57	ResearchPlanTextTemplate	5	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:50:38.564326	2024-02-16 08:50:38.564326
58	ReactionDescriptionTextTemplate	5	\N	{"_toolbar": ["ndash", "water-free", "resin-solvent", "resin-solvent-reagent", "hand-stop", "reaction-procedure", "gpx-a", "gpx-b", "washed-nahco3", "acidified-hcl", "tlc-control", "dried", "isolated", "residue-purified", "residue-adsorbed", "residue-dissolved"]}	\N	2024-02-16 08:50:38.572784	2024-02-16 08:50:38.572784
59	ElementTextTemplate	5	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:50:38.581746	2024-02-16 08:50:38.581746
60	SampleTextTemplate	6	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:51:22.310529	2024-02-16 08:51:22.310529
61	ReactionTextTemplate	6	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:51:22.317725	2024-02-16 08:51:22.317725
62	WellplateTextTemplate	6	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:51:22.325076	2024-02-16 08:51:22.325076
63	ScreenTextTemplate	6	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:51:22.333389	2024-02-16 08:51:22.333389
64	ResearchPlanTextTemplate	6	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:51:22.340885	2024-02-16 08:51:22.340885
65	ReactionDescriptionTextTemplate	6	\N	{"_toolbar": ["ndash", "water-free", "resin-solvent", "resin-solvent-reagent", "hand-stop", "reaction-procedure", "gpx-a", "gpx-b", "washed-nahco3", "acidified-hcl", "tlc-control", "dried", "isolated", "residue-purified", "residue-adsorbed", "residue-dissolved"]}	\N	2024-02-16 08:51:22.346546	2024-02-16 08:51:22.346546
66	ElementTextTemplate	6	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:51:22.361244	2024-02-16 08:51:22.361244
67	SampleTextTemplate	7	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:52:48.586156	2024-02-16 08:52:48.586156
68	ReactionTextTemplate	7	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:52:48.593692	2024-02-16 08:52:48.593692
69	WellplateTextTemplate	7	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:52:48.600937	2024-02-16 08:52:48.600937
70	ScreenTextTemplate	7	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:52:48.608637	2024-02-16 08:52:48.608637
71	ResearchPlanTextTemplate	7	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:52:48.615364	2024-02-16 08:52:48.615364
72	ReactionDescriptionTextTemplate	7	\N	{"_toolbar": ["ndash", "water-free", "resin-solvent", "resin-solvent-reagent", "hand-stop", "reaction-procedure", "gpx-a", "gpx-b", "washed-nahco3", "acidified-hcl", "tlc-control", "dried", "isolated", "residue-purified", "residue-adsorbed", "residue-dissolved"]}	\N	2024-02-16 08:52:48.620761	2024-02-16 08:52:48.620761
73	ElementTextTemplate	7	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:52:48.627358	2024-02-16 08:52:48.627358
74	SampleTextTemplate	8	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:53:15.397987	2024-02-16 08:53:15.397987
75	ReactionTextTemplate	8	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:53:15.40514	2024-02-16 08:53:15.40514
76	WellplateTextTemplate	8	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:53:15.412451	2024-02-16 08:53:15.412451
77	ScreenTextTemplate	8	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:53:15.419595	2024-02-16 08:53:15.419595
78	ResearchPlanTextTemplate	8	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:53:15.426594	2024-02-16 08:53:15.426594
79	ReactionDescriptionTextTemplate	8	\N	{"_toolbar": ["ndash", "water-free", "resin-solvent", "resin-solvent-reagent", "hand-stop", "reaction-procedure", "gpx-a", "gpx-b", "washed-nahco3", "acidified-hcl", "tlc-control", "dried", "isolated", "residue-purified", "residue-adsorbed", "residue-dissolved"]}	\N	2024-02-16 08:53:15.432318	2024-02-16 08:53:15.432318
80	ElementTextTemplate	8	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-02-16 08:53:15.43978	2024-02-16 08:53:15.43978
81	SampleTextTemplate	9	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-09-27 09:11:56.64858	2024-09-27 09:11:56.64858
82	ReactionTextTemplate	9	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-09-27 09:11:56.653746	2024-09-27 09:11:56.653746
83	WellplateTextTemplate	9	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-09-27 09:11:56.663147	2024-09-27 09:11:56.663147
84	ScreenTextTemplate	9	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-09-27 09:11:56.683374	2024-09-27 09:11:56.683374
85	ResearchPlanTextTemplate	9	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-09-27 09:11:56.703427	2024-09-27 09:11:56.703427
86	ReactionDescriptionTextTemplate	9	\N	{"_toolbar": ["ndash", "water-free", "resin-solvent", "resin-solvent-reagent", "hand-stop", "reaction-procedure", "gpx-a", "gpx-b", "washed-nahco3", "acidified-hcl", "tlc-control", "dried", "isolated", "residue-purified", "residue-adsorbed", "residue-dissolved"]}	\N	2024-09-27 09:11:56.715268	2024-09-27 09:11:56.715268
87	ElementTextTemplate	9	\N	{"MS": ["ei", "fab", "esi", "apci", "asap", "maldi", "m+", "hr", "hr-ei", "hr-fab"], "_toolbar": ["ndash", "h-nmr", "c-nmr", "ir", "uv", "ea"]}	\N	2024-09-27 09:11:56.729949	2024-09-27 09:11:56.729949
\.


--
-- Data for Name: third_party_apps; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.third_party_apps (id, url, name, file_types, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_affiliations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_affiliations (id, user_id, affiliation_id, created_at, updated_at, deleted_at, "from", "to", main) FROM stdin;
\.


--
-- Data for Name: user_labels; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_labels (id, user_id, title, description, color, access_level, "position", created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, email, encrypted_password, reset_password_token, reset_password_sent_at, remember_created_at, sign_in_count, current_sign_in_at, last_sign_in_at, current_sign_in_ip, last_sign_in_ip, created_at, updated_at, name, first_name, last_name, deleted_at, counters, name_abbreviation, type, reaction_name_prefix, confirmation_token, confirmed_at, confirmation_sent_at, unconfirmed_email, layout, selected_device_id, failed_attempts, unlock_token, locked_at, account_active, matrix, providers, is_super_device, used_space, allocated_space) FROM stdin;
3	m.starman@live.com	$2a$10$BzLw8xKsNz4oIS9mnNw7p.VzBcoRtdNX24IC/H6YN2Nctfy.QtuAC	\N	\N	\N	1	2024-01-23 15:13:20.641783	2024-01-23 15:13:20.641783	127.0.0.1	127.0.0.1	2024-01-23 15:12:19.918834	2024-01-23 15:13:20.642011	\N	Martin	Starman	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	MAS	Admin	R	xdBHzBM8ShSXkid_Wysz	2024-01-23 15:12:19.919039	2024-01-23 15:12:19.919011	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	98784	\N	f	0	0
2	martin.starman@kit.edu	$2a$10$Vzj0LeZcs6Ojh9g6wMIAh.oS8DPFtnrVkARiPbm8R8ujspcPMCyqW	\N	\N	\N	9	2024-02-16 08:49:52.776908	2024-01-25 08:40:05.47299	127.0.0.1	127.0.0.1	2024-01-23 15:12:02.229711	2024-02-16 08:49:52.777158	\N	Martin	Starman	\N	"try"=>"2", "samples"=>"1", "reactions"=>"0", "wellplates"=>"0"	MSU	Person	R	Ecq4xYuU-MsBRThdweV3	2024-01-23 15:12:02.230011	2024-01-23 15:12:02.229988	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	98784	\N	f	0	0
1	eln-admin@kit.edu	$2a$10$qE0IcYGPHz2WUsN2IvOEkuek6fUc7K5h.EGpECBmp8oMbq.qL1Q8y	\N	\N	\N	2	2024-01-24 07:01:08.96201	2024-01-23 13:45:57.853152	127.0.0.1	127.0.0.1	2024-01-23 13:44:00.404024	2024-01-24 07:01:08.962315	\N	ELN	Admin	\N	"samples"=>"0", "celllines"=>"0", "reactions"=>"0", "wellplates"=>"0"	ADM	Admin	R	\N	\N	\N	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	3	\N	\N	t	98784	\N	f	0	0
4	m.staran@live.com	$2a$10$83ZsXImGxdzkGSvoRF1C7uCc5R8pmpWMW9Wa0Q7sZpK/wI6TJuCBG	\N	\N	\N	5	2024-09-27 09:11:14.505259	2024-02-16 08:50:01.890402	172.19.0.1	127.0.0.1	2024-01-24 07:01:45.775235	2024-09-27 09:11:14.509955	\N	Martin	Starman	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	MSA	Admin	R	ix5afEaByUe6Ccs4QWMS	2024-01-24 07:01:45.775487	2024-01-24 07:01:45.775465	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	98784	\N	f	0	0
9	nicole.jung@kit.edu	$2a$10$M2D8zrllF9lIosSBjiDHxees6p8jbZPxFVl//34a8mKFjpt7fOtuS	\N	\N	\N	0	\N	\N	\N	\N	2024-09-27 09:11:56.592927	2024-09-27 09:11:56.592927	\N	Nicole	Jung	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	JNG	Person	R	K1TcbNdcGjZaEePsmXpc	2024-09-27 09:11:56.593003	2024-09-27 09:11:56.592979	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	98784	\N	f	0	0
8	admin@kit.edu	$2a$10$RaQTg0SutLSH5UR0ImRpZuXmFwLgqsU/WMXMqTO7aJfpz9h4UCAgu	\N	\N	\N	1	2024-11-20 06:20:14.569775	2024-11-20 06:20:14.569775	172.19.0.1	172.19.0.1	2024-02-16 08:53:15.375483	2024-11-20 06:20:14.569893	\N	Admin	User	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	ADI	Admin	R	iAfqy7KWJsZTX51WtYbF	2024-02-16 08:53:15.37572	2024-02-16 08:53:15.375696	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	98784	\N	f	0	0
5	td@kit.edu	$2a$10$H6mlnZXkBajzFg2cUabuRe.Rfinxjh8niL1XVPD5sSrXWhvAUb2cG	\N	\N	\N	0	\N	\N	\N	\N	2024-02-16 08:50:38.507891	2024-02-16 08:50:38.507891	\N	Test Device 1	T.D	2024-11-20 06:08:45.949671	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	TD	DeviceDeprecated	R	WZLhgByxwfLrutY8W6Zc	\N	2024-02-16 08:50:38.508079	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	\N	98784	\N	f	0	0
6	ad@git.edu	$2a$10$kyAy3TkHHh4qi.Iyf8eOzuRDGwy4unwo4rHk2O/BQXD5gKjCz85KW	\N	\N	\N	0	\N	\N	\N	\N	2024-02-16 08:51:22.295244	2024-02-16 08:51:24.672829	\N	Admin Device 2	A.Device	2024-11-20 06:08:45.949671	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	AD	DeviceDeprecated	R	Z4mD5X27fx6n7i6qfbSH	\N	2024-02-16 08:51:22.295298	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	\N	98784	\N	t	0	0
7	api@kit.edu	$2a$10$XJAIhBoWNwxvqOIAoXWZiO6/kcy3e2ZTrhWEbwhYn6Rs4wR7D95Ma	\N	\N	\N	4	2025-11-13 04:53:42.315766	2024-11-20 06:25:23.102417	172.23.0.1	172.19.0.1	2024-02-16 08:52:48.555419	2025-11-13 04:54:36.814753	\N	API	User	\N	"wrk"=>"3", "samples"=>"4", "reactions"=>"2", "wellplates"=>"0"	API	Person	R	4yRJG5yc33Gq6qpjr-p3	2024-02-16 08:52:48.555698	2024-02-16 08:52:48.555671	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	98784	\N	f	0	0
\.


--
-- Data for Name: users_admins; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users_admins (id, user_id, admin_id) FROM stdin;
\.


--
-- Data for Name: users_devices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users_devices (id, user_id, device_id) FROM stdin;
\.


--
-- Data for Name: users_groups; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users_groups (id, user_id, group_id) FROM stdin;
\.


--
-- Data for Name: vessel_templates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.vessel_templates (id, name, details, material_details, material_type, vessel_type, volume_amount, volume_unit, created_at, updated_at, deleted_at, weight_amount, weight_unit) FROM stdin;
\.


--
-- Data for Name: vessels; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.vessels (id, vessel_template_id, user_id, name, description, short_label, created_at, updated_at, deleted_at, bar_code, qr_code) FROM stdin;
\.


--
-- Data for Name: vocabularies; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.vocabularies (id, identifier, name, label, field_type, description, opid, term_id, source, source_id, layer_id, field_id, properties, created_by, created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: wellplates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.wellplates (id, name, description, created_at, updated_at, deleted_at, short_label, readout_titles, plain_text_description, width, height, log_data) FROM stdin;
\.


--
-- Data for Name: wells; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.wells (id, sample_id, wellplate_id, position_x, position_y, created_at, updated_at, additive, deleted_at, readouts, label, color_code, log_data) FROM stdin;
\.


--
-- Data for Name: mols; Type: TABLE DATA; Schema: rdkit; Owner: postgres
--

COPY rdkit.mols (id, m) FROM stdin;
1	N
2	N
3	B
4	Cc1cccc2ccccc12
5	Cc1cccc2ccccc12
6	N
\.


--
-- Name: affiliations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.affiliations_id_seq', 1, false);


--
-- Name: analyses_experiments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.analyses_experiments_id_seq', 1, false);


--
-- Name: attachments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.attachments_id_seq', 6, true);


--
-- Name: authentication_keys_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.authentication_keys_id_seq', 1, false);


--
-- Name: calendar_entries_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.calendar_entries_id_seq', 1, false);


--
-- Name: calendar_entry_notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.calendar_entry_notifications_id_seq', 1, false);


--
-- Name: cellline_materials_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.cellline_materials_id_seq', 1, false);


--
-- Name: cellline_samples_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.cellline_samples_id_seq', 1, false);


--
-- Name: channels_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.channels_id_seq', 24, true);


--
-- Name: chemicals_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.chemicals_id_seq', 1, false);


--
-- Name: collections_celllines_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_celllines_id_seq', 1, false);


--
-- Name: collections_device_descriptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_device_descriptions_id_seq', 1, false);


--
-- Name: collections_elements_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_elements_id_seq', 10, true);


--
-- Name: collections_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_id_seq', 13, true);


--
-- Name: collections_reactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_reactions_id_seq', 4, true);


--
-- Name: collections_research_plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_research_plans_id_seq', 1, false);


--
-- Name: collections_samples_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_samples_id_seq', 12, true);


--
-- Name: collections_screens_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_screens_id_seq', 1, false);


--
-- Name: collections_wellplates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_wellplates_id_seq', 1, false);


--
-- Name: collector_errors_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collector_errors_id_seq', 1, false);


--
-- Name: comments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.comments_id_seq', 1, false);


--
-- Name: computed_props_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.computed_props_id_seq', 1, false);


--
-- Name: containers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.containers_id_seq', 30, true);


--
-- Name: dataset_klasses_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.dataset_klasses_id_seq', 8, true);


--
-- Name: dataset_klasses_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.dataset_klasses_revisions_id_seq', 8, true);


--
-- Name: datasets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.datasets_id_seq', 1, false);


--
-- Name: datasets_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.datasets_revisions_id_seq', 1, false);


--
-- Name: delayed_jobs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.delayed_jobs_id_seq', 157, true);


--
-- Name: device_descriptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.device_descriptions_id_seq', 1, false);


--
-- Name: device_metadata_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.device_metadata_id_seq', 1, false);


--
-- Name: devices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.devices_id_seq', 7, true);


--
-- Name: element_klasses_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.element_klasses_id_seq', 10, true);


--
-- Name: element_klasses_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.element_klasses_revisions_id_seq', 15, true);


--
-- Name: element_tags_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.element_tags_id_seq', 16, true);


--
-- Name: elemental_compositions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.elemental_compositions_id_seq', 12, true);


--
-- Name: elements_elements_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.elements_elements_id_seq', 1, false);


--
-- Name: elements_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.elements_id_seq', 5, true);


--
-- Name: elements_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.elements_revisions_id_seq', 5, true);


--
-- Name: elements_samples_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.elements_samples_id_seq', 1, false);


--
-- Name: experiments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.experiments_id_seq', 1, false);


--
-- Name: fingerprints_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.fingerprints_id_seq', 3, true);


--
-- Name: inventories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.inventories_id_seq', 1, false);


--
-- Name: ketcherails_amino_acids_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ketcherails_amino_acids_id_seq', 1, false);


--
-- Name: ketcherails_atom_abbreviations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ketcherails_atom_abbreviations_id_seq', 1, false);


--
-- Name: ketcherails_common_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ketcherails_common_templates_id_seq', 161, true);


--
-- Name: ketcherails_custom_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ketcherails_custom_templates_id_seq', 1, false);


--
-- Name: ketcherails_template_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ketcherails_template_categories_id_seq', 1, false);


--
-- Name: layer_tracks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.layer_tracks_id_seq', 1, false);


--
-- Name: layers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.layers_id_seq', 1, false);


--
-- Name: literals_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.literals_id_seq', 1, false);


--
-- Name: literatures_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.literatures_id_seq', 1, false);


--
-- Name: matrices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.matrices_id_seq', 16, true);


--
-- Name: measurements_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.measurements_id_seq', 1, false);


--
-- Name: messages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.messages_id_seq', 1, false);


--
-- Name: metadata_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.metadata_id_seq', 1, false);


--
-- Name: molecule_names_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.molecule_names_id_seq', 7, true);


--
-- Name: molecules_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.molecules_id_seq', 3, true);


--
-- Name: nmr_sim_nmr_simulations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.nmr_sim_nmr_simulations_id_seq', 1, false);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.notifications_id_seq', 1, false);


--
-- Name: ols_terms_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ols_terms_id_seq', 1, false);


--
-- Name: pg_search_documents_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.pg_search_documents_id_seq', 13, true);


--
-- Name: predictions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.predictions_id_seq', 1, false);


--
-- Name: private_notes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.private_notes_id_seq', 1, false);


--
-- Name: profiles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.profiles_id_seq', 8, true);


--
-- Name: reactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reactions_id_seq', 2, true);


--
-- Name: reactions_samples_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reactions_samples_id_seq', 5, true);


--
-- Name: report_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.report_templates_id_seq', 7, true);


--
-- Name: reports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reports_id_seq', 1, false);


--
-- Name: reports_users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reports_users_id_seq', 1, false);


--
-- Name: research_plan_metadata_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.research_plan_metadata_id_seq', 1, false);


--
-- Name: research_plan_table_schemas_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.research_plan_table_schemas_id_seq', 1, false);


--
-- Name: research_plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.research_plans_id_seq', 1, false);


--
-- Name: research_plans_screens_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.research_plans_screens_id_seq', 1, false);


--
-- Name: research_plans_wellplates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.research_plans_wellplates_id_seq', 1, false);


--
-- Name: residues_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.residues_id_seq', 1, false);


--
-- Name: sample_tasks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sample_tasks_id_seq', 1, false);


--
-- Name: samples_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.samples_id_seq', 6, true);


--
-- Name: scan_results_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.scan_results_id_seq', 1, false);


--
-- Name: scifinder_n_credentials_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.scifinder_n_credentials_id_seq', 1, false);


--
-- Name: screens_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.screens_id_seq', 1, false);


--
-- Name: screens_wellplates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.screens_wellplates_id_seq', 1, false);


--
-- Name: segment_klasses_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.segment_klasses_id_seq', 2, true);


--
-- Name: segment_klasses_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.segment_klasses_revisions_id_seq', 4, true);


--
-- Name: segments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.segments_id_seq', 1, false);


--
-- Name: segments_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.segments_revisions_id_seq', 1, false);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.subscriptions_id_seq', 1, false);


--
-- Name: sync_collections_users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sync_collections_users_id_seq', 1, false);


--
-- Name: text_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.text_templates_id_seq', 87, true);


--
-- Name: third_party_apps_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.third_party_apps_id_seq', 1, false);


--
-- Name: user_affiliations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_affiliations_id_seq', 1, false);


--
-- Name: user_labels_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_labels_id_seq', 1, false);


--
-- Name: users_admins_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_admins_id_seq', 1, false);


--
-- Name: users_devices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_devices_id_seq', 1, false);


--
-- Name: users_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_groups_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 9, true);


--
-- Name: vocabularies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.vocabularies_id_seq', 1, false);


--
-- Name: wellplates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.wellplates_id_seq', 1, false);


--
-- Name: wells_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.wells_id_seq', 1, false);


--
-- Name: affiliations affiliations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.affiliations
    ADD CONSTRAINT affiliations_pkey PRIMARY KEY (id);


--
-- Name: analyses_experiments analyses_experiments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.analyses_experiments
    ADD CONSTRAINT analyses_experiments_pkey PRIMARY KEY (id);


--
-- Name: ar_internal_metadata ar_internal_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ar_internal_metadata
    ADD CONSTRAINT ar_internal_metadata_pkey PRIMARY KEY (key);


--
-- Name: attachments attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.attachments
    ADD CONSTRAINT attachments_pkey PRIMARY KEY (id);


--
-- Name: authentication_keys authentication_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.authentication_keys
    ADD CONSTRAINT authentication_keys_pkey PRIMARY KEY (id);


--
-- Name: calendar_entries calendar_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calendar_entries
    ADD CONSTRAINT calendar_entries_pkey PRIMARY KEY (id);


--
-- Name: calendar_entry_notifications calendar_entry_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calendar_entry_notifications
    ADD CONSTRAINT calendar_entry_notifications_pkey PRIMARY KEY (id);


--
-- Name: cellline_materials cellline_materials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cellline_materials
    ADD CONSTRAINT cellline_materials_pkey PRIMARY KEY (id);


--
-- Name: cellline_samples cellline_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cellline_samples
    ADD CONSTRAINT cellline_samples_pkey PRIMARY KEY (id);


--
-- Name: channels channels_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channels
    ADD CONSTRAINT channels_pkey PRIMARY KEY (id);


--
-- Name: chemicals chemicals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chemicals
    ADD CONSTRAINT chemicals_pkey PRIMARY KEY (id);


--
-- Name: code_logs code_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.code_logs
    ADD CONSTRAINT code_logs_pkey PRIMARY KEY (id);


--
-- Name: collections_celllines collections_celllines_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_celllines
    ADD CONSTRAINT collections_celllines_pkey PRIMARY KEY (id);


--
-- Name: collections_device_descriptions collections_device_descriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_device_descriptions
    ADD CONSTRAINT collections_device_descriptions_pkey PRIMARY KEY (id);


--
-- Name: collections_elements collections_elements_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_elements
    ADD CONSTRAINT collections_elements_pkey PRIMARY KEY (id);


--
-- Name: collections collections_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections
    ADD CONSTRAINT collections_pkey PRIMARY KEY (id);


--
-- Name: collections_reactions collections_reactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_reactions
    ADD CONSTRAINT collections_reactions_pkey PRIMARY KEY (id);


--
-- Name: collections_research_plans collections_research_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_research_plans
    ADD CONSTRAINT collections_research_plans_pkey PRIMARY KEY (id);


--
-- Name: collections_samples collections_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_samples
    ADD CONSTRAINT collections_samples_pkey PRIMARY KEY (id);


--
-- Name: collections_screens collections_screens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_screens
    ADD CONSTRAINT collections_screens_pkey PRIMARY KEY (id);


--
-- Name: collections_vessels collections_vessels_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_vessels
    ADD CONSTRAINT collections_vessels_pkey PRIMARY KEY (id);


--
-- Name: collections_wellplates collections_wellplates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections_wellplates
    ADD CONSTRAINT collections_wellplates_pkey PRIMARY KEY (id);


--
-- Name: collector_errors collector_errors_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collector_errors
    ADD CONSTRAINT collector_errors_pkey PRIMARY KEY (id);


--
-- Name: comments comments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comments
    ADD CONSTRAINT comments_pkey PRIMARY KEY (id);


--
-- Name: computed_props computed_props_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.computed_props
    ADD CONSTRAINT computed_props_pkey PRIMARY KEY (id);


--
-- Name: containers containers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.containers
    ADD CONSTRAINT containers_pkey PRIMARY KEY (id);


--
-- Name: dataset_klasses dataset_klasses_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dataset_klasses
    ADD CONSTRAINT dataset_klasses_pkey PRIMARY KEY (id);


--
-- Name: dataset_klasses_revisions dataset_klasses_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dataset_klasses_revisions
    ADD CONSTRAINT dataset_klasses_revisions_pkey PRIMARY KEY (id);


--
-- Name: datasets datasets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.datasets
    ADD CONSTRAINT datasets_pkey PRIMARY KEY (id);


--
-- Name: datasets_revisions datasets_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.datasets_revisions
    ADD CONSTRAINT datasets_revisions_pkey PRIMARY KEY (id);


--
-- Name: delayed_jobs delayed_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.delayed_jobs
    ADD CONSTRAINT delayed_jobs_pkey PRIMARY KEY (id);


--
-- Name: device_descriptions device_descriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_descriptions
    ADD CONSTRAINT device_descriptions_pkey PRIMARY KEY (id);


--
-- Name: device_metadata device_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.device_metadata
    ADD CONSTRAINT device_metadata_pkey PRIMARY KEY (id);


--
-- Name: devices devices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_pkey PRIMARY KEY (id);


--
-- Name: element_klasses element_klasses_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.element_klasses
    ADD CONSTRAINT element_klasses_pkey PRIMARY KEY (id);


--
-- Name: element_klasses_revisions element_klasses_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.element_klasses_revisions
    ADD CONSTRAINT element_klasses_revisions_pkey PRIMARY KEY (id);


--
-- Name: element_tags element_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.element_tags
    ADD CONSTRAINT element_tags_pkey PRIMARY KEY (id);


--
-- Name: elemental_compositions elemental_compositions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elemental_compositions
    ADD CONSTRAINT elemental_compositions_pkey PRIMARY KEY (id);


--
-- Name: elements_elements elements_elements_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements_elements
    ADD CONSTRAINT elements_elements_pkey PRIMARY KEY (id);


--
-- Name: elements elements_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements
    ADD CONSTRAINT elements_pkey PRIMARY KEY (id);


--
-- Name: elements_revisions elements_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements_revisions
    ADD CONSTRAINT elements_revisions_pkey PRIMARY KEY (id);


--
-- Name: elements_samples elements_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.elements_samples
    ADD CONSTRAINT elements_samples_pkey PRIMARY KEY (id);


--
-- Name: experiments experiments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.experiments
    ADD CONSTRAINT experiments_pkey PRIMARY KEY (id);


--
-- Name: fingerprints fingerprints_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fingerprints
    ADD CONSTRAINT fingerprints_pkey PRIMARY KEY (id);


--
-- Name: inventories inventories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventories
    ADD CONSTRAINT inventories_pkey PRIMARY KEY (id);


--
-- Name: ketcherails_amino_acids ketcherails_amino_acids_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_amino_acids
    ADD CONSTRAINT ketcherails_amino_acids_pkey PRIMARY KEY (id);


--
-- Name: ketcherails_atom_abbreviations ketcherails_atom_abbreviations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_atom_abbreviations
    ADD CONSTRAINT ketcherails_atom_abbreviations_pkey PRIMARY KEY (id);


--
-- Name: ketcherails_common_templates ketcherails_common_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_common_templates
    ADD CONSTRAINT ketcherails_common_templates_pkey PRIMARY KEY (id);


--
-- Name: ketcherails_custom_templates ketcherails_custom_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_custom_templates
    ADD CONSTRAINT ketcherails_custom_templates_pkey PRIMARY KEY (id);


--
-- Name: ketcherails_template_categories ketcherails_template_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ketcherails_template_categories
    ADD CONSTRAINT ketcherails_template_categories_pkey PRIMARY KEY (id);


--
-- Name: layer_tracks layer_tracks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.layer_tracks
    ADD CONSTRAINT layer_tracks_pkey PRIMARY KEY (id);


--
-- Name: layers layers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.layers
    ADD CONSTRAINT layers_pkey PRIMARY KEY (id);


--
-- Name: literals literals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.literals
    ADD CONSTRAINT literals_pkey PRIMARY KEY (id);


--
-- Name: literatures literatures_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.literatures
    ADD CONSTRAINT literatures_pkey PRIMARY KEY (id);


--
-- Name: matrices matrices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.matrices
    ADD CONSTRAINT matrices_pkey PRIMARY KEY (id);


--
-- Name: measurements measurements_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.measurements
    ADD CONSTRAINT measurements_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: metadata metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadata
    ADD CONSTRAINT metadata_pkey PRIMARY KEY (id);


--
-- Name: molecule_names molecule_names_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.molecule_names
    ADD CONSTRAINT molecule_names_pkey PRIMARY KEY (id);


--
-- Name: molecules molecules_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.molecules
    ADD CONSTRAINT molecules_pkey PRIMARY KEY (id);


--
-- Name: nmr_sim_nmr_simulations nmr_sim_nmr_simulations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.nmr_sim_nmr_simulations
    ADD CONSTRAINT nmr_sim_nmr_simulations_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: ols_terms ols_terms_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ols_terms
    ADD CONSTRAINT ols_terms_pkey PRIMARY KEY (id);


--
-- Name: pg_search_documents pg_search_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.pg_search_documents
    ADD CONSTRAINT pg_search_documents_pkey PRIMARY KEY (id);


--
-- Name: predictions predictions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.predictions
    ADD CONSTRAINT predictions_pkey PRIMARY KEY (id);


--
-- Name: private_notes private_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.private_notes
    ADD CONSTRAINT private_notes_pkey PRIMARY KEY (id);


--
-- Name: profiles profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);


--
-- Name: reactions reactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reactions
    ADD CONSTRAINT reactions_pkey PRIMARY KEY (id);


--
-- Name: reactions_samples reactions_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reactions_samples
    ADD CONSTRAINT reactions_samples_pkey PRIMARY KEY (id);


--
-- Name: report_templates report_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.report_templates
    ADD CONSTRAINT report_templates_pkey PRIMARY KEY (id);


--
-- Name: reports reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_pkey PRIMARY KEY (id);


--
-- Name: reports_users reports_users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reports_users
    ADD CONSTRAINT reports_users_pkey PRIMARY KEY (id);


--
-- Name: research_plan_metadata research_plan_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plan_metadata
    ADD CONSTRAINT research_plan_metadata_pkey PRIMARY KEY (id);


--
-- Name: research_plan_table_schemas research_plan_table_schemas_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plan_table_schemas
    ADD CONSTRAINT research_plan_table_schemas_pkey PRIMARY KEY (id);


--
-- Name: research_plans research_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plans
    ADD CONSTRAINT research_plans_pkey PRIMARY KEY (id);


--
-- Name: research_plans_screens research_plans_screens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plans_screens
    ADD CONSTRAINT research_plans_screens_pkey PRIMARY KEY (id);


--
-- Name: research_plans_wellplates research_plans_wellplates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.research_plans_wellplates
    ADD CONSTRAINT research_plans_wellplates_pkey PRIMARY KEY (id);


--
-- Name: residues residues_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.residues
    ADD CONSTRAINT residues_pkey PRIMARY KEY (id);


--
-- Name: sample_tasks sample_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sample_tasks
    ADD CONSTRAINT sample_tasks_pkey PRIMARY KEY (id);


--
-- Name: samples samples_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.samples
    ADD CONSTRAINT samples_pkey PRIMARY KEY (id);


--
-- Name: scan_results scan_results_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scan_results
    ADD CONSTRAINT scan_results_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: scifinder_n_credentials scifinder_n_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scifinder_n_credentials
    ADD CONSTRAINT scifinder_n_credentials_pkey PRIMARY KEY (id);


--
-- Name: screens screens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.screens
    ADD CONSTRAINT screens_pkey PRIMARY KEY (id);


--
-- Name: screens_wellplates screens_wellplates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.screens_wellplates
    ADD CONSTRAINT screens_wellplates_pkey PRIMARY KEY (id);


--
-- Name: segment_klasses segment_klasses_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segment_klasses
    ADD CONSTRAINT segment_klasses_pkey PRIMARY KEY (id);


--
-- Name: segment_klasses_revisions segment_klasses_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segment_klasses_revisions
    ADD CONSTRAINT segment_klasses_revisions_pkey PRIMARY KEY (id);


--
-- Name: segments segments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_pkey PRIMARY KEY (id);


--
-- Name: segments_revisions segments_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.segments_revisions
    ADD CONSTRAINT segments_revisions_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: sync_collections_users sync_collections_users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sync_collections_users
    ADD CONSTRAINT sync_collections_users_pkey PRIMARY KEY (id);


--
-- Name: text_templates text_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.text_templates
    ADD CONSTRAINT text_templates_pkey PRIMARY KEY (id);


--
-- Name: third_party_apps third_party_apps_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.third_party_apps
    ADD CONSTRAINT third_party_apps_pkey PRIMARY KEY (id);


--
-- Name: user_affiliations user_affiliations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_affiliations
    ADD CONSTRAINT user_affiliations_pkey PRIMARY KEY (id);


--
-- Name: user_labels user_labels_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_labels
    ADD CONSTRAINT user_labels_pkey PRIMARY KEY (id);


--
-- Name: users_admins users_admins_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users_admins
    ADD CONSTRAINT users_admins_pkey PRIMARY KEY (id);


--
-- Name: users_devices users_devices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users_devices
    ADD CONSTRAINT users_devices_pkey PRIMARY KEY (id);


--
-- Name: users_groups users_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users_groups
    ADD CONSTRAINT users_groups_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: vessel_templates vessel_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vessel_templates
    ADD CONSTRAINT vessel_templates_pkey PRIMARY KEY (id);


--
-- Name: vessels vessels_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vessels
    ADD CONSTRAINT vessels_pkey PRIMARY KEY (id);


--
-- Name: vocabularies vocabularies_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vocabularies
    ADD CONSTRAINT vocabularies_pkey PRIMARY KEY (id);


--
-- Name: wellplates wellplates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.wellplates
    ADD CONSTRAINT wellplates_pkey PRIMARY KEY (id);


--
-- Name: wells wells_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.wells
    ADD CONSTRAINT wells_pkey PRIMARY KEY (id);


--
-- Name: container_anc_desc_udx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX container_anc_desc_udx ON public.container_hierarchies USING btree (ancestor_id, descendant_id, generations);


--
-- Name: container_desc_idx; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX container_desc_idx ON public.container_hierarchies USING btree (descendant_id);


--
-- Name: delayed_jobs_priority; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX delayed_jobs_priority ON public.delayed_jobs USING btree (priority, run_at);


--
-- Name: index_attachments_on_attachable_type_and_attachable_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_attachments_on_attachable_type_and_attachable_id ON public.attachments USING btree (attachable_type, attachable_id);


--
-- Name: index_attachments_on_identifier; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_attachments_on_identifier ON public.attachments USING btree (identifier);


--
-- Name: index_authentication_keys_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_authentication_keys_on_user_id ON public.authentication_keys USING btree (user_id);


--
-- Name: index_calendar_entries_on_created_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_calendar_entries_on_created_by ON public.calendar_entries USING btree (created_by);


--
-- Name: index_calendar_entries_on_eventable_type_and_eventable_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_calendar_entries_on_eventable_type_and_eventable_id ON public.calendar_entries USING btree (eventable_type, eventable_id);


--
-- Name: index_calendar_entry_notifications_on_calendar_entry_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_calendar_entry_notifications_on_calendar_entry_id ON public.calendar_entry_notifications USING btree (calendar_entry_id);


--
-- Name: index_calendar_entry_notifications_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_calendar_entry_notifications_on_user_id ON public.calendar_entry_notifications USING btree (user_id);


--
-- Name: index_cellline_materials_on_name_and_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_cellline_materials_on_name_and_source ON public.cellline_materials USING btree (name, source);


--
-- Name: index_cellline_samples_on_ancestry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_cellline_samples_on_ancestry ON public.cellline_samples USING btree (ancestry);


--
-- Name: index_code_logs_on_source_and_source_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_code_logs_on_source_and_source_id ON public.code_logs USING btree (source, source_id);


--
-- Name: index_collections_celllines_on_cellsample_id_and_coll_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_celllines_on_cellsample_id_and_coll_id ON public.collections_celllines USING btree (cellline_sample_id, collection_id);


--
-- Name: index_collections_celllines_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_celllines_on_collection_id ON public.collections_celllines USING btree (collection_id);


--
-- Name: index_collections_celllines_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_celllines_on_deleted_at ON public.collections_celllines USING btree (deleted_at);


--
-- Name: index_collections_device_descriptions_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_device_descriptions_on_collection_id ON public.collections_device_descriptions USING btree (collection_id);


--
-- Name: index_collections_device_descriptions_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_device_descriptions_on_deleted_at ON public.collections_device_descriptions USING btree (deleted_at);


--
-- Name: index_collections_elements_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_elements_on_collection_id ON public.collections_elements USING btree (collection_id);


--
-- Name: index_collections_elements_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_elements_on_deleted_at ON public.collections_elements USING btree (deleted_at);


--
-- Name: index_collections_elements_on_element_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_elements_on_element_id ON public.collections_elements USING btree (element_id);


--
-- Name: index_collections_elements_on_element_id_and_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_elements_on_element_id_and_collection_id ON public.collections_elements USING btree (element_id, collection_id);


--
-- Name: index_collections_on_ancestry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_on_ancestry ON public.collections USING btree (ancestry);


--
-- Name: index_collections_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_on_deleted_at ON public.collections USING btree (deleted_at);


--
-- Name: index_collections_on_inventory_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_on_inventory_id ON public.collections USING btree (inventory_id);


--
-- Name: index_collections_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_on_user_id ON public.collections USING btree (user_id);


--
-- Name: index_collections_reactions_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_reactions_on_collection_id ON public.collections_reactions USING btree (collection_id);


--
-- Name: index_collections_reactions_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_reactions_on_deleted_at ON public.collections_reactions USING btree (deleted_at);


--
-- Name: index_collections_reactions_on_reaction_id_and_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_reactions_on_reaction_id_and_collection_id ON public.collections_reactions USING btree (reaction_id, collection_id);


--
-- Name: index_collections_research_plans_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_research_plans_on_collection_id ON public.collections_research_plans USING btree (collection_id);


--
-- Name: index_collections_research_plans_on_rplan_id_and_coll_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_research_plans_on_rplan_id_and_coll_id ON public.collections_research_plans USING btree (research_plan_id, collection_id);


--
-- Name: index_collections_samples_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_samples_on_collection_id ON public.collections_samples USING btree (collection_id);


--
-- Name: index_collections_samples_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_samples_on_deleted_at ON public.collections_samples USING btree (deleted_at);


--
-- Name: index_collections_samples_on_sample_id_and_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_samples_on_sample_id_and_collection_id ON public.collections_samples USING btree (sample_id, collection_id);


--
-- Name: index_collections_screens_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_screens_on_collection_id ON public.collections_screens USING btree (collection_id);


--
-- Name: index_collections_screens_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_screens_on_deleted_at ON public.collections_screens USING btree (deleted_at);


--
-- Name: index_collections_screens_on_screen_id_and_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_screens_on_screen_id_and_collection_id ON public.collections_screens USING btree (screen_id, collection_id);


--
-- Name: index_collections_vessels_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_vessels_on_collection_id ON public.collections_vessels USING btree (collection_id);


--
-- Name: index_collections_vessels_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_vessels_on_deleted_at ON public.collections_vessels USING btree (deleted_at);


--
-- Name: index_collections_vessels_on_vessel_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_vessels_on_vessel_id ON public.collections_vessels USING btree (vessel_id);


--
-- Name: index_collections_vessels_on_vessel_id_and_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_vessels_on_vessel_id_and_collection_id ON public.collections_vessels USING btree (vessel_id, collection_id);


--
-- Name: index_collections_wellplates_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_wellplates_on_collection_id ON public.collections_wellplates USING btree (collection_id);


--
-- Name: index_collections_wellplates_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_collections_wellplates_on_deleted_at ON public.collections_wellplates USING btree (deleted_at);


--
-- Name: index_collections_wellplates_on_wellplate_id_and_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_collections_wellplates_on_wellplate_id_and_collection_id ON public.collections_wellplates USING btree (wellplate_id, collection_id);


--
-- Name: index_comments_on_commentable_type_and_commentable_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_comments_on_commentable_type_and_commentable_id ON public.comments USING btree (commentable_type, commentable_id);


--
-- Name: index_comments_on_section; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_comments_on_section ON public.comments USING btree (section);


--
-- Name: index_comments_on_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_comments_on_user ON public.comments USING btree (created_by);


--
-- Name: index_computed_props_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_computed_props_on_deleted_at ON public.computed_props USING btree (deleted_at);


--
-- Name: index_containers_on_containable; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_containers_on_containable ON public.containers USING btree (containable_type, containable_id);


--
-- Name: index_dataset_klasses_revisions_on_dataset_klass_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_dataset_klasses_revisions_on_dataset_klass_id ON public.dataset_klasses_revisions USING btree (dataset_klass_id);


--
-- Name: index_datasets_revisions_on_dataset_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_datasets_revisions_on_dataset_id ON public.datasets_revisions USING btree (dataset_id);


--
-- Name: index_device_descriptions_on_ancestry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_device_descriptions_on_ancestry ON public.device_descriptions USING btree (ancestry);


--
-- Name: index_device_descriptions_on_device_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_device_descriptions_on_device_id ON public.device_descriptions USING btree (device_id);


--
-- Name: index_device_metadata_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_device_metadata_on_deleted_at ON public.device_metadata USING btree (deleted_at);


--
-- Name: index_device_metadata_on_device_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_device_metadata_on_device_id ON public.device_metadata USING btree (device_id);


--
-- Name: index_devices_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_devices_on_deleted_at ON public.devices USING btree (deleted_at);


--
-- Name: index_devices_on_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_devices_on_email ON public.devices USING btree (email);


--
-- Name: index_devices_on_name_abbreviation; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_devices_on_name_abbreviation ON public.devices USING btree (name_abbreviation) WHERE (name_abbreviation IS NOT NULL);


--
-- Name: index_element_klasses_revisions_on_element_klass_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_element_klasses_revisions_on_element_klass_id ON public.element_klasses_revisions USING btree (element_klass_id);


--
-- Name: index_element_tags_on_taggable_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_element_tags_on_taggable_id ON public.element_tags USING btree (taggable_id);


--
-- Name: index_elemental_compositions_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_elemental_compositions_on_sample_id ON public.elemental_compositions USING btree (sample_id);


--
-- Name: index_elements_elements_on_element_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_elements_elements_on_element_id ON public.elements_elements USING btree (element_id);


--
-- Name: index_elements_elements_on_parent_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_elements_elements_on_parent_id ON public.elements_elements USING btree (parent_id);


--
-- Name: index_elements_revisions_on_element_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_elements_revisions_on_element_id ON public.elements_revisions USING btree (element_id);


--
-- Name: index_elements_samples_on_element_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_elements_samples_on_element_id ON public.elements_samples USING btree (element_id);


--
-- Name: index_elements_samples_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_elements_samples_on_sample_id ON public.elements_samples USING btree (sample_id);


--
-- Name: index_inventories_on_prefix; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_inventories_on_prefix ON public.inventories USING btree (prefix);


--
-- Name: index_ketcherails_amino_acids_on_moderated_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_amino_acids_on_moderated_by ON public.ketcherails_amino_acids USING btree (moderated_by);


--
-- Name: index_ketcherails_amino_acids_on_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_amino_acids_on_name ON public.ketcherails_amino_acids USING btree (name);


--
-- Name: index_ketcherails_amino_acids_on_suggested_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_amino_acids_on_suggested_by ON public.ketcherails_amino_acids USING btree (suggested_by);


--
-- Name: index_ketcherails_atom_abbreviations_on_moderated_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_atom_abbreviations_on_moderated_by ON public.ketcherails_atom_abbreviations USING btree (moderated_by);


--
-- Name: index_ketcherails_atom_abbreviations_on_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_atom_abbreviations_on_name ON public.ketcherails_atom_abbreviations USING btree (name);


--
-- Name: index_ketcherails_atom_abbreviations_on_suggested_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_atom_abbreviations_on_suggested_by ON public.ketcherails_atom_abbreviations USING btree (suggested_by);


--
-- Name: index_ketcherails_common_templates_on_moderated_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_common_templates_on_moderated_by ON public.ketcherails_common_templates USING btree (moderated_by);


--
-- Name: index_ketcherails_common_templates_on_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_common_templates_on_name ON public.ketcherails_common_templates USING btree (name);


--
-- Name: index_ketcherails_common_templates_on_suggested_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_common_templates_on_suggested_by ON public.ketcherails_common_templates USING btree (suggested_by);


--
-- Name: index_ketcherails_custom_templates_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ketcherails_custom_templates_on_user_id ON public.ketcherails_custom_templates USING btree (user_id);


--
-- Name: index_layers_on_identifier; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_layers_on_identifier ON public.layers USING btree (identifier);


--
-- Name: index_layers_on_label; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_layers_on_label ON public.layers USING btree (label);


--
-- Name: index_layers_on_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_layers_on_name ON public.layers USING btree (name);


--
-- Name: index_layers_on_properties; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_layers_on_properties ON public.layers USING gin (properties);


--
-- Name: index_literatures_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_literatures_on_deleted_at ON public.literatures USING btree (deleted_at);


--
-- Name: index_matrices_on_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_matrices_on_name ON public.matrices USING btree (name);


--
-- Name: index_measurements_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_measurements_on_deleted_at ON public.measurements USING btree (deleted_at);


--
-- Name: index_measurements_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_measurements_on_sample_id ON public.measurements USING btree (sample_id);


--
-- Name: index_measurements_on_source_type_and_source_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_measurements_on_source_type_and_source_id ON public.measurements USING btree (source_type, source_id);


--
-- Name: index_measurements_on_well_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_measurements_on_well_id ON public.measurements USING btree (well_id);


--
-- Name: index_molecule_names_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_molecule_names_on_deleted_at ON public.molecule_names USING btree (deleted_at);


--
-- Name: index_molecule_names_on_molecule_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_molecule_names_on_molecule_id ON public.molecule_names USING btree (molecule_id);


--
-- Name: index_molecule_names_on_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_molecule_names_on_name ON public.molecule_names USING btree (name);


--
-- Name: index_molecule_names_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_molecule_names_on_user_id ON public.molecule_names USING btree (user_id);


--
-- Name: index_molecule_names_on_user_id_and_molecule_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_molecule_names_on_user_id_and_molecule_id ON public.molecule_names USING btree (user_id, molecule_id);


--
-- Name: index_molecules_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_molecules_on_deleted_at ON public.molecules USING btree (deleted_at);


--
-- Name: index_molecules_on_formula_and_inchikey_and_is_partial; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_molecules_on_formula_and_inchikey_and_is_partial ON public.molecules USING btree (inchikey, sum_formular, is_partial);


--
-- Name: index_nmr_sim_nmr_simulations_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_nmr_sim_nmr_simulations_on_deleted_at ON public.nmr_sim_nmr_simulations USING btree (deleted_at);


--
-- Name: index_nmr_sim_nmr_simulations_on_molecule_id_and_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_nmr_sim_nmr_simulations_on_molecule_id_and_source ON public.nmr_sim_nmr_simulations USING btree (molecule_id, source);


--
-- Name: index_notifications_on_message_id_and_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_notifications_on_message_id_and_user_id ON public.notifications USING btree (message_id, user_id);


--
-- Name: index_ols_terms_on_ancestry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_ols_terms_on_ancestry ON public.ols_terms USING btree (ancestry);


--
-- Name: index_ols_terms_on_owl_name_and_term_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_ols_terms_on_owl_name_and_term_id ON public.ols_terms USING btree (owl_name, term_id);


--
-- Name: index_on_device_description_and_collection; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_on_device_description_and_collection ON public.collections_device_descriptions USING btree (device_description_id, collection_id);


--
-- Name: index_on_element_literature; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_on_element_literature ON public.literals USING btree (element_type, element_id, literature_id, category);


--
-- Name: index_on_literature; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_on_literature ON public.literals USING btree (literature_id, element_type, element_id);


--
-- Name: index_pg_search_documents_on_searchable_type_and_searchable_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_pg_search_documents_on_searchable_type_and_searchable_id ON public.pg_search_documents USING btree (searchable_type, searchable_id);


--
-- Name: index_predefined_template; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_predefined_template ON public.text_templates USING btree (name) WHERE ((type)::text = 'PredefinedTextTemplate'::text);


--
-- Name: index_predictions_on_decision; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_predictions_on_decision ON public.predictions USING gin (decision);


--
-- Name: index_predictions_on_predictable_type_and_predictable_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_predictions_on_predictable_type_and_predictable_id ON public.predictions USING btree (predictable_type, predictable_id);


--
-- Name: index_private_note_on_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_private_note_on_user ON public.private_notes USING btree (created_by);


--
-- Name: index_private_notes_on_noteable_type_and_noteable_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_private_notes_on_noteable_type_and_noteable_id ON public.private_notes USING btree (noteable_type, noteable_id);


--
-- Name: index_profiles_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_profiles_on_deleted_at ON public.profiles USING btree (deleted_at);


--
-- Name: index_profiles_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_profiles_on_user_id ON public.profiles USING btree (user_id);


--
-- Name: index_reactions_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reactions_on_deleted_at ON public.reactions USING btree (deleted_at);


--
-- Name: index_reactions_on_rinchi_short_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reactions_on_rinchi_short_key ON public.reactions USING btree (rinchi_short_key DESC);


--
-- Name: index_reactions_on_rinchi_web_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reactions_on_rinchi_web_key ON public.reactions USING btree (rinchi_web_key);


--
-- Name: index_reactions_on_role; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reactions_on_role ON public.reactions USING btree (role);


--
-- Name: index_reactions_on_rxno; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reactions_on_rxno ON public.reactions USING btree (rxno DESC);


--
-- Name: index_reactions_samples_on_reaction_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reactions_samples_on_reaction_id ON public.reactions_samples USING btree (reaction_id);


--
-- Name: index_reactions_samples_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reactions_samples_on_sample_id ON public.reactions_samples USING btree (sample_id);


--
-- Name: index_report_templates_on_attachment_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_report_templates_on_attachment_id ON public.report_templates USING btree (attachment_id);


--
-- Name: index_reports_on_author_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reports_on_author_id ON public.reports USING btree (author_id);


--
-- Name: index_reports_on_file_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reports_on_file_name ON public.reports USING btree (file_name);


--
-- Name: index_reports_on_report_templates_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reports_on_report_templates_id ON public.reports USING btree (report_templates_id);


--
-- Name: index_reports_users_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reports_users_on_deleted_at ON public.reports_users USING btree (deleted_at);


--
-- Name: index_reports_users_on_report_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reports_users_on_report_id ON public.reports_users USING btree (report_id);


--
-- Name: index_reports_users_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_reports_users_on_user_id ON public.reports_users USING btree (user_id);


--
-- Name: index_research_plan_metadata_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_research_plan_metadata_on_deleted_at ON public.research_plan_metadata USING btree (deleted_at);


--
-- Name: index_research_plan_metadata_on_research_plan_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_research_plan_metadata_on_research_plan_id ON public.research_plan_metadata USING btree (research_plan_id);


--
-- Name: index_research_plans_screens_on_research_plan_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_research_plans_screens_on_research_plan_id ON public.research_plans_screens USING btree (research_plan_id);


--
-- Name: index_research_plans_screens_on_screen_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_research_plans_screens_on_screen_id ON public.research_plans_screens USING btree (screen_id);


--
-- Name: index_research_plans_wellplates_on_research_plan_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_research_plans_wellplates_on_research_plan_id ON public.research_plans_wellplates USING btree (research_plan_id);


--
-- Name: index_research_plans_wellplates_on_wellplate_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_research_plans_wellplates_on_wellplate_id ON public.research_plans_wellplates USING btree (wellplate_id);


--
-- Name: index_residues_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_residues_on_sample_id ON public.residues USING btree (sample_id);


--
-- Name: index_sample_tasks_on_creator_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_sample_tasks_on_creator_id ON public.sample_tasks USING btree (creator_id);


--
-- Name: index_sample_tasks_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_sample_tasks_on_sample_id ON public.sample_tasks USING btree (sample_id);


--
-- Name: index_samples_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_samples_on_deleted_at ON public.samples USING btree (deleted_at);


--
-- Name: index_samples_on_identifier; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_samples_on_identifier ON public.samples USING btree (identifier);


--
-- Name: index_samples_on_inventory_sample; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_samples_on_inventory_sample ON public.samples USING btree (inventory_sample);


--
-- Name: index_samples_on_molecule_name_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_samples_on_molecule_name_id ON public.samples USING btree (molecule_name_id);


--
-- Name: index_samples_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_samples_on_sample_id ON public.samples USING btree (molecule_id);


--
-- Name: index_samples_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_samples_on_user_id ON public.samples USING btree (user_id);


--
-- Name: index_scan_results_on_sample_task_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_scan_results_on_sample_task_id ON public.scan_results USING btree (sample_task_id);


--
-- Name: index_screens_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_screens_on_deleted_at ON public.screens USING btree (deleted_at);


--
-- Name: index_screens_wellplates_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_screens_wellplates_on_deleted_at ON public.screens_wellplates USING btree (deleted_at);


--
-- Name: index_screens_wellplates_on_screen_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_screens_wellplates_on_screen_id ON public.screens_wellplates USING btree (screen_id);


--
-- Name: index_screens_wellplates_on_wellplate_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_screens_wellplates_on_wellplate_id ON public.screens_wellplates USING btree (wellplate_id);


--
-- Name: index_segment_klasses_revisions_on_segment_klass_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_segment_klasses_revisions_on_segment_klass_id ON public.segment_klasses_revisions USING btree (segment_klass_id);


--
-- Name: index_segments_revisions_on_segment_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_segments_revisions_on_segment_id ON public.segments_revisions USING btree (segment_id);


--
-- Name: index_subscriptions_on_channel_id_and_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_subscriptions_on_channel_id_and_user_id ON public.subscriptions USING btree (channel_id, user_id);


--
-- Name: index_sync_collections_users_on_collection_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_sync_collections_users_on_collection_id ON public.sync_collections_users USING btree (collection_id);


--
-- Name: index_sync_collections_users_on_shared_by_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_sync_collections_users_on_shared_by_id ON public.sync_collections_users USING btree (shared_by_id, user_id, fake_ancestry);


--
-- Name: index_sync_collections_users_on_user_id_and_fake_ancestry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_sync_collections_users_on_user_id_and_fake_ancestry ON public.sync_collections_users USING btree (user_id, fake_ancestry);


--
-- Name: index_text_templates_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_text_templates_on_deleted_at ON public.text_templates USING btree (deleted_at);


--
-- Name: index_text_templates_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_text_templates_on_user_id ON public.text_templates USING btree (user_id);


--
-- Name: index_third_party_apps_on_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_third_party_apps_on_name ON public.third_party_apps USING btree (name);


--
-- Name: index_users_admins_on_admin_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_users_admins_on_admin_id ON public.users_admins USING btree (admin_id);


--
-- Name: index_users_admins_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_users_admins_on_user_id ON public.users_admins USING btree (user_id);


--
-- Name: index_users_groups_on_group_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_users_groups_on_group_id ON public.users_groups USING btree (group_id);


--
-- Name: index_users_groups_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_users_groups_on_user_id ON public.users_groups USING btree (user_id);


--
-- Name: index_users_on_confirmation_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_users_on_confirmation_token ON public.users USING btree (confirmation_token);


--
-- Name: index_users_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_users_on_deleted_at ON public.users USING btree (deleted_at);


--
-- Name: index_users_on_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_users_on_email ON public.users USING btree (email);


--
-- Name: index_users_on_name_abbreviation; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_users_on_name_abbreviation ON public.users USING btree (name_abbreviation) WHERE (name_abbreviation IS NOT NULL);


--
-- Name: index_users_on_reset_password_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_users_on_reset_password_token ON public.users USING btree (reset_password_token);


--
-- Name: index_users_on_unlock_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_users_on_unlock_token ON public.users USING btree (unlock_token);


--
-- Name: index_vessel_templates_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_vessel_templates_on_deleted_at ON public.vessel_templates USING btree (deleted_at);


--
-- Name: index_vessels_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_vessels_on_deleted_at ON public.vessels USING btree (deleted_at);


--
-- Name: index_vessels_on_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_vessels_on_user_id ON public.vessels USING btree (user_id);


--
-- Name: index_vessels_on_vessel_template_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_vessels_on_vessel_template_id ON public.vessels USING btree (vessel_template_id);


--
-- Name: index_wellplates_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_wellplates_on_deleted_at ON public.wellplates USING btree (deleted_at);


--
-- Name: index_wells_on_deleted_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_wells_on_deleted_at ON public.wells USING btree (deleted_at);


--
-- Name: index_wells_on_sample_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_wells_on_sample_id ON public.wells USING btree (sample_id);


--
-- Name: index_wells_on_wellplate_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX index_wells_on_wellplate_id ON public.wells USING btree (wellplate_id);


--
-- Name: uni_scifinder_n_credentials; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX uni_scifinder_n_credentials ON public.scifinder_n_credentials USING btree (created_by);


--
-- Name: index_rdkit.mols_on_m; Type: INDEX; Schema: rdkit; Owner: postgres
--

CREATE INDEX "index_rdkit.mols_on_m" ON rdkit.mols USING gist (m);


--
-- Name: layers lab_trg_layers_changes; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER lab_trg_layers_changes AFTER UPDATE ON public.layers FOR EACH ROW EXECUTE FUNCTION public.lab_record_layers_changes();


--
-- Name: attachments logidze_on_attachments; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_attachments BEFORE INSERT OR UPDATE ON public.attachments FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: chemicals logidze_on_chemicals; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_chemicals BEFORE INSERT OR UPDATE ON public.chemicals FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: containers logidze_on_containers; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_containers BEFORE INSERT OR UPDATE ON public.containers FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: device_descriptions logidze_on_device_descriptions; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_device_descriptions BEFORE INSERT OR UPDATE ON public.device_descriptions FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: elemental_compositions logidze_on_elemental_compositions; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_elemental_compositions BEFORE INSERT OR UPDATE ON public.elemental_compositions FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: reactions logidze_on_reactions; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_reactions BEFORE INSERT OR UPDATE ON public.reactions FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: reactions_samples logidze_on_reactions_samples; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_reactions_samples BEFORE INSERT OR UPDATE ON public.reactions_samples FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: research_plan_metadata logidze_on_research_plan_metadata; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_research_plan_metadata BEFORE INSERT OR UPDATE ON public.research_plan_metadata FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: research_plans logidze_on_research_plans; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_research_plans BEFORE INSERT OR UPDATE ON public.research_plans FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: research_plans_wellplates logidze_on_research_plans_wellplates; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_research_plans_wellplates BEFORE INSERT OR UPDATE ON public.research_plans_wellplates FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: residues logidze_on_residues; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_residues BEFORE INSERT OR UPDATE ON public.residues FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: samples logidze_on_samples; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_samples BEFORE INSERT OR UPDATE ON public.samples FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: screens logidze_on_screens; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_screens BEFORE INSERT OR UPDATE ON public.screens FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: wellplates logidze_on_wellplates; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_wellplates BEFORE INSERT OR UPDATE ON public.wellplates FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: wells logidze_on_wells; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER logidze_on_wells BEFORE INSERT OR UPDATE ON public.wells FOR EACH ROW WHEN ((COALESCE(current_setting('logidze.disabled'::text, true), ''::text) <> 'on'::text)) EXECUTE FUNCTION public.logidze_logger('null', 'updated_at');


--
-- Name: samples set_samples_mol_rdkit_trg; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER set_samples_mol_rdkit_trg BEFORE INSERT OR UPDATE ON public.samples FOR EACH ROW EXECUTE FUNCTION public.set_samples_mol_rdkit();


--
-- Name: matrices update_users_matrix_trg; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_users_matrix_trg AFTER INSERT OR UPDATE ON public.matrices FOR EACH ROW EXECUTE FUNCTION public.update_users_matrix();


--
-- Name: layer_tracks fk_rails_19f5918b95; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.layer_tracks
    ADD CONSTRAINT fk_rails_19f5918b95 FOREIGN KEY (identifier) REFERENCES public.layers(identifier);


--
-- Name: sample_tasks fk_rails_5f034c53c2; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sample_tasks
    ADD CONSTRAINT fk_rails_5f034c53c2 FOREIGN KEY (creator_id) REFERENCES public.users(id);


--
-- Name: literals fk_rails_a065c2905f; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.literals
    ADD CONSTRAINT fk_rails_a065c2905f FOREIGN KEY (literature_id) REFERENCES public.literatures(id);


--
-- Name: report_templates fk_rails_b549b8ae9d; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.report_templates
    ADD CONSTRAINT fk_rails_b549b8ae9d FOREIGN KEY (attachment_id) REFERENCES public.attachments(id);


--
-- Name: collections fk_rails_f05d27b2ca; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.collections
    ADD CONSTRAINT fk_rails_f05d27b2ca FOREIGN KEY (inventory_id) REFERENCES public.inventories(id);


--
-- Name: sample_tasks fk_rails_fcf255019c; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sample_tasks
    ADD CONSTRAINT fk_rails_fcf255019c FOREIGN KEY (sample_id) REFERENCES public.samples(id);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- PostgreSQL database dump complete
--

\unrestrict f22ngLBAWGP6AwBHkdbHHDUdnpvZi1kKTg3VqrpCoVgTuVnIOnNgVmEWJzhT6xf

