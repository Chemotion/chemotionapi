--
-- PostgreSQL database dump
--

-- Dumped from database version 14.13 (Debian 14.13-1.pgdg120+1)
-- Dumped by pg_dump version 16.6 (Ubuntu 16.6-0ubuntu0.24.04.1)

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
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner:
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


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
                                    con_state integer
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
                                           updated_at timestamp(6) without time zone NOT NULL
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
                                         short_label character varying
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
                                  chemical_data jsonb
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
                                    inventory_id bigint
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
                                   plain_text_content text
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
                                               updated_at timestamp without time zone
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
                                    prefix character varying NOT NULL,
                                    name character varying NOT NULL,
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
                                  variations jsonb DEFAULT '[]'::jsonb,
                                  plain_text_description text,
                                  plain_text_observation text,
                                  gaseous boolean DEFAULT false,
                                  vessel_size jsonb DEFAULT '{"unit": "ml", "amount": null}'::jsonb
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
                                inventory_sample boolean DEFAULT false
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
                              is_super_device boolean DEFAULT false
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
                                          gas_phase_data jsonb DEFAULT '{"time": {"unit": "h", "value": null}, "temperature": {"unit": "°C", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}'::jsonb
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
                                               related_identifier jsonb
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
                                       body jsonb
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
                                                  deleted_at timestamp without time zone
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
                                 updated_at timestamp without time zone NOT NULL
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
                                plain_text_description text
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
                                               celllinesample_detail_level integer DEFAULT 10
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
                                   height integer DEFAULT 8
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
                              color_code character varying
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

COPY public.attachments (id, attachable_id, filename, identifier, checksum, storage, created_by, created_for, version, created_at, updated_at, content_type, bucket, key, thumb, folder, attachable_type, aasm_state, filesize, attachment_data, con_state) FROM stdin;
3	\N	Supporting_information.docx	0f51d8d9-1e59-43d4-97be-636c2b3e543a	\N	local	1	1	\N	2024-01-23 13:44:02.233976	2024-01-23 13:44:02.233976	\N	\N	7fdb104e-ab44-4a86-b992-5a9703d3f493	f	\N	\N	non_jcamp	\N	{"id": "1/0f51d8d9-1e59-43d4-97be-636c2b3e543a", "storage": "store", "metadata": {"md5": "c255a111db2b80cff9eba396be7de06e", "size": 32417, "filename": "Supporting_information.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N
4	\N	Spectra.docx	7e0def2f-c9d4-4074-91d9-b26ab5495719	\N	local	1	1	\N	2024-01-23 13:44:02.243392	2024-01-23 13:44:02.243392	\N	\N	4cf7d09d-7641-4f75-bf11-2ca69995ba3f	f	\N	\N	non_jcamp	\N	{"id": "1/7e0def2f-c9d4-4074-91d9-b26ab5495719", "storage": "store", "metadata": {"md5": "b9720669839497ede31b37dff86daf08", "size": 32379, "filename": "Spectra.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N
5	\N	rxn_list.html.erb	40161613-40ff-48b9-ae0d-be5a1ec2474d	\N	local	1	1	\N	2024-01-23 13:44:02.257439	2024-01-23 13:44:02.257439	\N	\N	08cb29e1-887e-4813-9c58-6d87366952a0	f	\N	\N	non_jcamp	\N	{"id": "1/40161613-40ff-48b9-ae0d-be5a1ec2474d", "storage": "store", "metadata": {"md5": "a85bab1410123d7bd636599f664aa235", "size": 2310, "filename": "rxn_list.html.erb", "mime_type": "text/html"}}	\N
6	\N	Standard.docx	32ba77e7-5962-44cf-b2e5-1dda89f302a3	\N	local	1	1	\N	2024-01-23 13:44:02.298977	2024-01-23 13:44:02.298977	application/vnd.openxmlformats-officedocument.wordprocessingml.document	\N	db0add32-4336-4a3e-94f3-f19b07693ad2	f	\N	\N	non_jcamp	\N	{"id": "1/32ba77e7-5962-44cf-b2e5-1dda89f302a3", "storage": "store", "metadata": {"md5": "2595f44a2dc963d58d7e32cdc5861980", "size": 93876, "filename": "Standard.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N
1	\N	Standard.docx	67e79caf-a9a2-4096-894f-5e2c571d32e2	\N	local	1	1	\N	2024-01-23 13:44:02.200237	2024-01-23 13:44:02.200237	\N	\N	21241e81-8131-42a2-8f0e-5d7a31a61054	f	\N	\N	non_jcamp	\N	{"id": "1/67e79caf-a9a2-4096-894f-5e2c571d32e2", "storage": "store", "metadata": {"md5": "2595f44a2dc963d58d7e32cdc5861980", "size": 93876, "filename": "Standard.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N
2	\N	Supporting_information.docx	631520ee-cd61-45db-af4f-2f4af5efb80b	\N	local	1	1	\N	2024-01-23 13:44:02.223474	2024-01-23 13:44:02.223474	\N	\N	d7ba6c50-6ed6-4415-b8f2-d0bd7b38575d	f	\N	\N	non_jcamp	\N	{"id": "1/631520ee-cd61-45db-af4f-2f4af5efb80b", "storage": "store", "metadata": {"md5": "c255a111db2b80cff9eba396be7de06e", "size": 32417, "filename": "Supporting_information.docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}	\N
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

COPY public.cellline_materials (id, name, source, cell_type, organism, tissue, disease, growth_medium, biosafety_level, variant, mutation, optimal_growth_temp, cryo_pres_medium, gender, description, deleted_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: cellline_samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cellline_samples (id, cellline_material_id, cellline_sample_id, amount, unit, passage, contamination, name, description, user_id, deleted_at, created_at, updated_at, short_label) FROM stdin;
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

COPY public.chemicals (id, sample_id, cas, chemical_data) FROM stdin;
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
\.


--
-- Data for Name: collections; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections (id, user_id, ancestry, label, shared_by_id, is_shared, permission_level, sample_detail_level, reaction_detail_level, wellplate_detail_level, created_at, updated_at, "position", screen_detail_level, is_locked, deleted_at, is_synchronized, researchplan_detail_level, element_detail_level, tabs_segment, celllinesample_detail_level, inventory_id) FROM stdin;
1	2	\N	chemotion-repository.net	\N	f	0	10	10	10	2024-01-23 15:12:02.256553	2024-01-23 15:12:02.256553	1	10	t	\N	f	10	10	{}	10	\N
3	3	\N	All	\N	f	0	10	10	10	2024-01-23 15:12:19.921883	2024-01-23 15:12:19.921883	0	10	t	\N	f	10	10	{}	10	\N
5	4	\N	All	\N	f	0	10	10	10	2024-01-24 07:01:45.778925	2024-01-24 07:01:45.778925	0	10	t	\N	f	10	10	{}	10	\N
4	2	\N	TEST 1	\N	f	0	10	10	10	2024-01-23 15:17:02.666049	2024-01-24 08:41:10.845282	1	10	f	\N	f	10	10	{"sample": {"results": 5, "analyses": 2, "properties": 1, "references": 4, "qc_curation": 3, "measurements": -1}}	10	\N
2	2	\N	All	\N	f	0	10	10	10	2024-01-23 15:12:02.26009	2024-01-25 10:10:02.777475	0	10	t	\N	f	10	10	{"try": {"TrySeg1": 2, "analyses": 3, "properties": 1, "attachments": 4}, "sample": {"results": 5, "analyses": 1, "properties": 3, "references": 4, "qc_curation": 2, "measurements": -1}}	10	\N
6	5	\N	All	\N	f	0	10	10	10	2024-02-16 08:50:38.511259	2024-02-16 08:50:38.511259	0	10	t	\N	f	10	10	{}	10	\N
7	6	\N	All	\N	f	0	10	10	10	2024-02-16 08:51:22.298693	2024-02-16 08:51:22.298693	0	10	t	\N	f	10	10	{}	10	\N
8	7	\N	chemotion-repository.net	\N	f	0	10	10	10	2024-02-16 08:52:48.558915	2024-02-16 08:52:48.558915	1	10	t	\N	f	10	10	{}	10	\N
9	7	\N	All	\N	f	0	10	10	10	2024-02-16 08:52:48.561313	2024-02-16 08:52:48.561313	0	10	t	\N	f	10	10	{}	10	\N
10	8	\N	All	\N	f	0	10	10	10	2024-02-16 08:53:15.379007	2024-02-16 08:53:15.379007	0	10	t	\N	f	10	10	{}	10	\N
11	7	\N	FIXED	\N	f	0	10	10	10	2024-03-21 10:31:23.524241	2024-03-21 10:40:57.388683	1	10	f	\N	f	10	10	{}	10	\N
12	9	\N	chemotion-repository.net	\N	f	0	10	10	10	2024-09-27 09:11:56.595124	2024-09-27 09:11:56.595124	1	10	t	\N	f	10	10	{}	10	\N
13	9	\N	All	\N	f	0	10	10	10	2024-09-27 09:11:56.596278	2024-09-27 09:11:56.596278	0	10	t	\N	f	10	10	{}	10	\N
\.


--
-- Data for Name: collections_celllines; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.collections_celllines (id, collection_id, cellline_sample_id, deleted_at) FROM stdin;
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
\.


--
-- Data for Name: containers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.containers (id, ancestry, containable_id, containable_type, name, container_type, description, extended_metadata, created_at, updated_at, parent_id, plain_text_content) FROM stdin;
1	\N	2	User	inbox	root	\N		2024-01-23 15:16:40.246973	2024-01-23 15:16:40.273554	\N	\N
3	\N	\N	\N	new	analyses		"report"=>"true"	2024-01-23 15:17:46.337888	2024-01-23 15:17:46.337888	2	\N
2	\N	1	Sample	\N	\N	\N		2024-01-23 15:17:46.323082	2024-01-23 15:17:46.441102	\N	\N
5	\N	\N	\N	new	analyses		"report"=>"true"	2024-01-24 08:17:12.606606	2024-01-24 08:17:12.606606	4	\N
4	\N	1	Labimotion::Element	\N	\N	\N		2024-01-24 08:17:12.591497	2024-01-24 08:17:12.627644	\N	\N
7	\N	\N	\N	new	analyses		"report"=>"true"	2024-02-16 08:49:01.378426	2024-02-16 08:49:01.378426	6	\N
6	\N	2	Labimotion::Element	\N	\N			2024-02-16 08:49:01.352578	2024-02-16 08:49:01.398714	\N	\N
8	\N	7	User	inbox	root	\N		2024-02-16 09:48:37.45738	2024-02-16 09:48:37.480074	\N	\N
10	\N	\N	\N	new	analyses		"report"=>"true"	2024-03-21 10:32:02.11686	2024-03-21 10:32:02.11686	9	\N
9	\N	3	Labimotion::Element	\N	\N			2024-03-21 10:32:02.092653	2024-03-21 10:32:02.138395	\N	\N
12	\N	\N	\N	new	analyses		"report"=>"true"	2024-03-21 10:41:42.596332	2024-03-21 10:41:42.596332	11	\N
11	\N	4	Labimotion::Element	\N	\N			2024-03-21 10:41:42.572604	2024-03-21 10:41:42.617244	\N	\N
14	\N	\N	\N	new	analyses		"report"=>"true"	2024-03-21 12:13:25.314721	2024-03-21 12:13:25.314721	13	\N
13	\N	5	Labimotion::Element	\N	\N			2024-03-21 12:13:25.292371	2024-03-21 12:13:25.333296	\N	\N
15	\N	2	Sample	\N	\N			2024-11-20 06:11:55.274029	2024-11-20 06:11:55.320363	\N	\N
17	\N	3	Sample	\N	\N			2024-11-20 06:12:56.606384	2024-11-20 06:12:56.654722	\N	\N
19	\N	4	Sample	\N	\N			2024-11-20 06:14:15.765622	2024-11-20 06:14:15.815153	\N	\N
21	\N	1	Reaction	\N	\N			2024-11-20 06:14:26.398815	2024-11-20 06:14:26.414076	\N	\N
16	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:11:55.286131	2024-11-20 06:14:26.436514	15	\N
18	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:12:56.627518	2024-11-20 06:14:26.462635	17	\N
20	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:14:15.783372	2024-11-20 06:14:26.488333	19	\N
22	\N	\N	\N	new	analyses		"kind"=>NULL, "index"=>NULL, "report"=>"true", "status"=>NULL, "instrument"=>NULL	2024-11-20 06:14:26.408483	2024-11-20 06:15:17.636943	21	\N
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
118	0	0	--- !ruby/object:ActiveJob::QueueAdapters::DelayedJobAdapter::JobWrapper\njob_data:\n  job_class: PubchemCidJob\n  job_id: de585b0d-07bc-4595-a809-d19760fb2c74\n  provider_job_id: \n  queue_name: pubchem\n  priority: \n  arguments: []\n  executions: 0\n  exception_executions: {}\n  locale: en\n  timezone: UTC\n  enqueued_at: '2024-12-04T14:58:07Z'\n	\N	2024-12-08 05:46:00	\N	\N	\N	pubchem	2024-12-04 14:58:07.244423	2024-12-04 14:58:07.244423	46 5 * * 7
119	0	0	--- !ruby/object:ActiveJob::QueueAdapters::DelayedJobAdapter::JobWrapper\njob_data:\n  job_class: PubchemLcssJob\n  job_id: 6cf6035f-3cbe-48e4-a5b8-af73287eedd7\n  provider_job_id: \n  queue_name: pubchemLcss\n  priority: \n  arguments: []\n  executions: 0\n  exception_executions: {}\n  locale: en\n  timezone: UTC\n  enqueued_at: '2024-12-04T14:58:07Z'\n	\N	2024-12-07 01:17:00	\N	\N	\N	pubchemLcss	2024-12-04 14:58:07.252247	2024-12-04 14:58:07.252247	17 1 * * 6
120	0	0	--- !ruby/object:ActiveJob::QueueAdapters::DelayedJobAdapter::JobWrapper\njob_data:\n  job_class: RefreshElementTagJob\n  job_id: a713f760-a749-4081-844e-0eaf0ce73313\n  provider_job_id: \n  queue_name: refresh_element_tag\n  priority: \n  arguments: []\n  executions: 0\n  exception_executions: {}\n  locale: en\n  timezone: UTC\n  enqueued_at: '2024-12-04T14:58:07Z'\n	\N	2024-12-08 23:42:00	\N	\N	\N	refresh_element_tag	2024-12-04 14:58:07.262739	2024-12-04 14:58:07.262739	42 23 * * 7
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
\.


--
-- Data for Name: elemental_compositions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.elemental_compositions (id, sample_id, composition_type, data, loading, created_at, updated_at) FROM stdin;
1	1	found		\N	2024-01-23 15:17:46.443292	2024-01-23 15:17:46.443292
2	1	formula	"H"=>"17.76", "N"=>"82.24"	\N	2024-01-23 15:17:46.445584	2024-01-23 15:17:46.445584
3	2	found		\N	2024-11-20 06:11:55.321262	2024-11-20 06:11:55.321262
4	2	formula	"H"=>"17.76", "N"=>"82.24"	\N	2024-11-20 06:11:55.32201	2024-11-20 06:11:55.32201
5	3	found		\N	2024-11-20 06:12:56.655652	2024-11-20 06:12:56.655652
6	3	formula	"B"=>"78.14", "H"=>"21.86"	\N	2024-11-20 06:12:56.656432	2024-11-20 06:12:56.656432
7	4	found		\N	2024-11-20 06:14:15.816253	2024-11-20 06:14:15.816253
8	4	formula	"C"=>"92.91", "H"=>"7.09"	\N	2024-11-20 06:14:15.816797	2024-11-20 06:14:15.816797
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

COPY public.reactions (id, name, created_at, updated_at, description, timestamp_start, timestamp_stop, observation, purification, dangerous_products, tlc_solvents, tlc_description, rf_value, temperature, status, reaction_svg_file, solvent, deleted_at, short_label, created_by, role, origin, rinchi_string, rinchi_long_key, rinchi_short_key, rinchi_web_key, duration, rxno, conditions, variations, plain_text_description, plain_text_observation, gaseous, vessel_size) FROM stdin;
1		2024-11-20 06:14:26.377705	2024-11-20 06:15:51.753287	--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\nops:\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\n  insert: "\\n"\n			--- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\nops:\n- !ruby/hash:ActiveSupport::HashWithIndifferentAccess\n  insert: "\\n"\n	{}	{}			0	{"data": [], "userText": "", "valueUnit": "°C"}		ed612b54b097d204efc8df601ea8b808e3741b66b1ca286a3a9f32d781a71685.svg		\N	API-R1	7		{}	RInChI=1.00.1S/C11H10/c1-9-5-4-7-10-6-2-3-8-11(9)10/h2-8H,1H3<>H3N/h1H3<>BH3/h1H3/d-	Long-RInChIKey=SA-BUHFF-QPUYECUOLPXSFR-UHFFFAOYSA-N--QGZKDVFQNNGYKY-UHFFFAOYSA-N--UORVGPXVDQYIDP-UHFFFAOYSA-N	Short-RInChIKey=SA-BUHFF-QPUYECUOLP-QGZKDVFQNN-UORVGPXVDQ-NUHFF-NUHFF-NUHFF-ZZZ	Web-RInChIKey=QIYMARWDEZAJTNBIR-NUHFFFADPSCTJSA				[{"id": 1, "notes": "", "analyses": [], "products": {"4": {"aux": {"yield": 0, "purity": 1, "loading": null, "molarity": 0, "equivalent": null, "sumFormula": "C11H10", "coefficient": 1, "isReference": false, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": null}, "amount": {"unit": "mol", "value": 0}, "volume": {"unit": "l", "value": 0}}}, "solvents": {}, "reactants": {"3": {"aux": {"yield": null, "purity": 1, "loading": null, "molarity": 0, "equivalent": 0.0013540885967435786, "sumFormula": "BH3", "coefficient": 1, "isReference": false, "molecularWeight": 13.83482}, "mass": {"unit": "g", "value": 0.022}, "amount": {"unit": "mol", "value": 0.0015901905481965069}, "volume": {"unit": "l", "value": 0.000022}}}, "properties": {"duration": {"unit": "Second(s)", "value": 2}, "temperature": {"unit": "°C", "value": 1}}, "startingMaterials": {"2": {"aux": {"yield": null, "purity": 1, "loading": null, "molarity": 0, "equivalent": null, "sumFormula": "H3N", "coefficient": 1, "isReference": true, "molecularWeight": 17.03052}, "mass": {"unit": "g", "value": 20}, "amount": {"unit": "mol", "value": 1.1743622625733097}, "volume": {"unit": "l", "value": 0}}}}, {"id": 2, "notes": "", "analyses": [], "products": {"4": {"aux": {"yield": 0, "purity": 1, "loading": null, "molarity": 0, "equivalent": null, "sumFormula": "C11H10", "coefficient": 1, "isReference": false, "molecularWeight": 142.19710000000003}, "mass": {"unit": "g", "value": null}, "amount": {"unit": "mol", "value": 0}, "volume": {"unit": "l", "value": 0}}}, "solvents": {}, "reactants": {"3": {"aux": {"yield": null, "purity": 1, "loading": null, "molarity": 0, "equivalent": 0.13540885967435787, "sumFormula": "BH3", "coefficient": 1, "isReference": false, "molecularWeight": 13.83482}, "mass": {"unit": "g", "value": 0.022}, "amount": {"unit": "mol", "value": 0.0015901905481965069}, "volume": {"unit": "l", "value": 0.000022}}}, "properties": {"duration": {"unit": "Second(s)", "value": 2}, "temperature": {"unit": "°C", "value": 2}}, "startingMaterials": {"2": {"aux": {"yield": null, "purity": 1, "loading": null, "molarity": 0, "equivalent": null, "sumFormula": "H3N", "coefficient": 1, "isReference": true, "molecularWeight": 17.03052}, "mass": {"unit": "g", "value": 0.2}, "amount": {"unit": "mol", "value": 0.011743622625733096}, "volume": {"unit": "l", "value": 0}}}}]			f	{"unit": "ml", "amount": null}
\.


--
-- Data for Name: reactions_samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reactions_samples (id, reaction_id, sample_id, reference, equivalent, "position", type, deleted_at, waste, coefficient, show_label, gas_type, gas_phase_data) FROM stdin;
1	1	2	t	1	0	ReactionsStartingMaterialSample	\N	f	1	f	\N	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}
3	1	4	f	0	0	ReactionsProductSample	\N	f	1	f	\N	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}
2	1	3	f	0	0	ReactionsReactantSample	\N	f	1	f	\N	{"time": {"unit": "h", "value": null}, "temperature": {"unit": "K", "value": null}, "turnover_number": null, "part_per_million": null, "turnover_frequency": {"unit": "TON/h", "value": null}}
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

COPY public.research_plan_metadata (id, research_plan_id, doi, url, landing_page, title, type, publisher, publication_year, dates, created_at, updated_at, deleted_at, data_cite_prefix, data_cite_created_at, data_cite_updated_at, data_cite_version, data_cite_last_response, data_cite_state, data_cite_creator_name, description, creator, affiliation, contributor, language, rights, format, version, geo_location, funding_reference, subject, alternate_identifier, related_identifier) FROM stdin;
\.


--
-- Data for Name: research_plan_table_schemas; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plan_table_schemas (id, name, value, created_by, deleted_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: research_plans; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plans (id, name, created_by, deleted_at, created_at, updated_at, body) FROM stdin;
\.


--
-- Data for Name: research_plans_screens; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plans_screens (screen_id, research_plan_id, id, created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: research_plans_wellplates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.research_plans_wellplates (research_plan_id, wellplate_id, id, created_at, updated_at, deleted_at) FROM stdin;
\.


--
-- Data for Name: residues; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.residues (id, sample_id, residue_type, custom_info, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: sample_tasks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sample_tasks (id, result_value, result_unit, description, creator_id, sample_id, created_at, updated_at, required_scan_results) FROM stdin;
\.


--
-- Data for Name: samples; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.samples (id, name, target_amount_value, target_amount_unit, created_at, updated_at, description, molecule_id, molfile, purity, deprecated_solvent, impurities, location, is_top_secret, ancestry, external_label, created_by, short_label, real_amount_value, real_amount_unit, imported_readout, deleted_at, sample_svg_file, user_id, identifier, density, melting_point, boiling_point, fingerprint_id, xref, molarity_value, molarity_unit, molecule_name_id, molfile_version, stereo, metrics, decoupled, molecular_mass, sum_formula, solvent, dry_solvent, inventory_sample) FROM stdin;
1	\N	0	g	2024-01-23 15:17:46.412096	2024-01-23 15:17:46.412096		1	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	1				f	\N		2	MSU-1	\N	g	\N	\N	\N	\N	\N	0	(,)	(,)	1	{}	0	M	3	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f
2	\N	0	g	2024-11-20 06:11:55.311593	2024-11-20 06:11:55.311593		1	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e30303030204e202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	1				f	\N		7	API-1	\N	g	\N	\N	\N	\N	\N	0	(,)	(,)	1	{}	0	M	2	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f
3	\N	0.022	g	2024-11-20 06:12:56.646234	2024-11-20 06:14:26.471014		2	\\x0a202020202052444b69742020202020202020202032440a0a2020312020302020302020302020302020302020302020302020302020303939392056323030300a20202020302e3030303020202020302e3030303020202020302e303030302042202020302020302020302020302020302020302020302020302020302020302020302020300a4d2020454e44	1				f	\N		7	reactant	\N	g	\N	\N	\N	\N	\N	1	(,)	(,)	2	{}	0	M	4	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f
4	API-R1-A	0	g	2024-11-20 06:14:15.809067	2024-11-20 06:14:26.498125		3	\\x0a20204b657463686572203131323032343037313432442031202020312e30303030302020202020302e30303030302020202020300a0a2031312031322020302020202020302020302020202020202020202020203939392056323030300a20202020342e363530302020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020352e353136302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020332e373834302020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832312020202d322e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d322e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020372e323438312020202d332e3732353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020362e333832302020202d342e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a20202020342e363530302020202d312e3232353020202020302e303030302043202020302020302020302020302020302020302020302020302020302020302020302020300a2020312020322020312020302020202020302020300a2020322020332020312020302020202020302020300a2020332020342020312020302020202020302020300a2020342020352020322020302020202020302020300a2020352020362020312020302020202020302020300a2020362020312020322020302020202020302020300a2020322020372020322020302020202020302020300a2020372020382020312020302020202020302020300a2020382020392020322020302020202020302020300a2020392031302020312020302020202020302020300a2031302020332020322020302020202020302020300a2020312031312020312020302020202020302020300a4d2020454e440a242424240a0a	1				f	\N		7	API-3	\N	g	\N	\N	18bb8133763ad42880d28d267b93f23f6fa48d34516d5c966d8f28c05efe8b8458ebae6f5f1fd5f3581fdab74f1b9b443eb8869ed46b8b067eedae28cfb3245f.svg	\N	\N	0	(,)	(,)	3	{}	0	M	6	\N	{"abs": "any", "rel": "any"}	mmm	f	0		[]	f	f
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
\.


--
-- Data for Name: scifinder_n_credentials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.scifinder_n_credentials (id, access_token, refresh_token, expires_at, created_by, updated_at) FROM stdin;
\.


--
-- Data for Name: screens; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.screens (id, description, name, result, collaborator, conditions, requirements, created_at, updated_at, deleted_at, component_graph_data, plain_text_description) FROM stdin;
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

COPY public.sync_collections_users (id, user_id, collection_id, shared_by_id, permission_level, sample_detail_level, reaction_detail_level, wellplate_detail_level, screen_detail_level, fake_ancestry, researchplan_detail_level, label, created_at, updated_at, element_detail_level, celllinesample_detail_level) FROM stdin;
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

COPY public.users (id, email, encrypted_password, reset_password_token, reset_password_sent_at, remember_created_at, sign_in_count, current_sign_in_at, last_sign_in_at, current_sign_in_ip, last_sign_in_ip, created_at, updated_at, name, first_name, last_name, deleted_at, counters, name_abbreviation, type, reaction_name_prefix, confirmation_token, confirmed_at, confirmation_sent_at, unconfirmed_email, layout, selected_device_id, failed_attempts, unlock_token, locked_at, account_active, matrix, providers, is_super_device) FROM stdin;
3	m.starman@live.com	$2a$10$BzLw8xKsNz4oIS9mnNw7p.VzBcoRtdNX24IC/H6YN2Nctfy.QtuAC	\N	\N	\N	1	2024-01-23 15:13:20.641783	2024-01-23 15:13:20.641783	127.0.0.1	127.0.0.1	2024-01-23 15:12:19.918834	2024-01-23 15:13:20.642011	\N	Martin	Starman	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	MAS	Admin	R	xdBHzBM8ShSXkid_Wysz	2024-01-23 15:12:19.919039	2024-01-23 15:12:19.919011	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	33248	\N	f
2	martin.starman@kit.edu	$2a$10$Vzj0LeZcs6Ojh9g6wMIAh.oS8DPFtnrVkARiPbm8R8ujspcPMCyqW	\N	\N	\N	9	2024-02-16 08:49:52.776908	2024-01-25 08:40:05.47299	127.0.0.1	127.0.0.1	2024-01-23 15:12:02.229711	2024-02-16 08:49:52.777158	\N	Martin	Starman	\N	"try"=>"2", "samples"=>"1", "reactions"=>"0", "wellplates"=>"0"	MSU	Person	R	Ecq4xYuU-MsBRThdweV3	2024-01-23 15:12:02.230011	2024-01-23 15:12:02.229988	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	33248	\N	f
1	eln-admin@kit.edu	$2a$10$qE0IcYGPHz2WUsN2IvOEkuek6fUc7K5h.EGpECBmp8oMbq.qL1Q8y	\N	\N	\N	2	2024-01-24 07:01:08.96201	2024-01-23 13:45:57.853152	127.0.0.1	127.0.0.1	2024-01-23 13:44:00.404024	2024-01-24 07:01:08.962315	\N	ELN	Admin	\N	"samples"=>"0", "celllines"=>"0", "reactions"=>"0", "wellplates"=>"0"	ADM	Admin	R	\N	\N	\N	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	3	\N	\N	t	33248	\N	f
4	m.staran@live.com	$2a$10$83ZsXImGxdzkGSvoRF1C7uCc5R8pmpWMW9Wa0Q7sZpK/wI6TJuCBG	\N	\N	\N	5	2024-09-27 09:11:14.505259	2024-02-16 08:50:01.890402	172.19.0.1	127.0.0.1	2024-01-24 07:01:45.775235	2024-09-27 09:11:14.509955	\N	Martin	Starman	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	MSA	Admin	R	ix5afEaByUe6Ccs4QWMS	2024-01-24 07:01:45.775487	2024-01-24 07:01:45.775465	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	33248	\N	f
9	nicole.jung@kit.edu	$2a$10$M2D8zrllF9lIosSBjiDHxees6p8jbZPxFVl//34a8mKFjpt7fOtuS	\N	\N	\N	0	\N	\N	\N	\N	2024-09-27 09:11:56.592927	2024-09-27 09:11:56.592927	\N	Nicole	Jung	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	JNG	Person	R	K1TcbNdcGjZaEePsmXpc	2024-09-27 09:11:56.593003	2024-09-27 09:11:56.592979	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	33248	\N	f
5	td@kit.edu	$2a$10$H6mlnZXkBajzFg2cUabuRe.Rfinxjh8niL1XVPD5sSrXWhvAUb2cG	\N	\N	\N	0	\N	\N	\N	\N	2024-02-16 08:50:38.507891	2024-02-16 08:50:38.507891	\N	Test Device 1	T.D	2024-11-20 06:08:45.949671	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	TD	Device	R	WZLhgByxwfLrutY8W6Zc	\N	2024-02-16 08:50:38.508079	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	\N	33248	\N	f
6	ad@git.edu	$2a$10$kyAy3TkHHh4qi.Iyf8eOzuRDGwy4unwo4rHk2O/BQXD5gKjCz85KW	\N	\N	\N	0	\N	\N	\N	\N	2024-02-16 08:51:22.295244	2024-02-16 08:51:24.672829	\N	Admin Device 2	A.Device	2024-11-20 06:08:45.949671	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	AD	Device	R	Z4mD5X27fx6n7i6qfbSH	\N	2024-02-16 08:51:22.295298	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	\N	33248	\N	t
8	admin@kit.edu	$2a$10$RaQTg0SutLSH5UR0ImRpZuXmFwLgqsU/WMXMqTO7aJfpz9h4UCAgu	\N	\N	\N	1	2024-11-20 06:20:14.569775	2024-11-20 06:20:14.569775	172.19.0.1	172.19.0.1	2024-02-16 08:53:15.375483	2024-11-20 06:20:14.569893	\N	Admin	User	\N	"samples"=>"0", "reactions"=>"0", "wellplates"=>"0"	ADI	Admin	R	iAfqy7KWJsZTX51WtYbF	2024-02-16 08:53:15.37572	2024-02-16 08:53:15.375696	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	33248	\N	f
7	api@kit.edu	$2a$10$XJAIhBoWNwxvqOIAoXWZiO6/kcy3e2ZTrhWEbwhYn6Rs4wR7D95Ma	\N	\N	\N	3	2024-11-20 06:25:23.102417	2024-11-20 06:09:37.801289	172.19.0.1	172.19.0.1	2024-02-16 08:52:48.555419	2024-11-20 06:25:23.102665	\N	API	User	\N	"wrk"=>"3", "samples"=>"3", "reactions"=>"1", "wellplates"=>"0"	API	Person	R	4yRJG5yc33Gq6qpjr-p3	2024-02-16 08:52:48.555698	2024-02-16 08:52:48.555671	\N	"sample"=>"1", "screen"=>"4", "reaction"=>"2", "wellplate"=>"3", "research_plan"=>"5"	\N	0	\N	\N	t	33248	\N	f
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
-- Data for Name: wellplates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.wellplates (id, name, description, created_at, updated_at, deleted_at, short_label, readout_titles, plain_text_description, width, height) FROM stdin;
\.


--
-- Data for Name: wells; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.wells (id, sample_id, wellplate_id, position_x, position_y, created_at, updated_at, additive, deleted_at, readouts, label, color_code) FROM stdin;
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

SELECT pg_catalog.setval('public.collections_reactions_id_seq', 2, true);


--
-- Name: collections_research_plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_research_plans_id_seq', 1, false);


--
-- Name: collections_samples_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.collections_samples_id_seq', 8, true);


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

SELECT pg_catalog.setval('public.containers_id_seq', 22, true);


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

SELECT pg_catalog.setval('public.delayed_jobs_id_seq', 120, true);


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

SELECT pg_catalog.setval('public.element_klasses_id_seq', 9, true);


--
-- Name: element_klasses_revisions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.element_klasses_revisions_id_seq', 15, true);


--
-- Name: element_tags_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.element_tags_id_seq', 13, true);


--
-- Name: elemental_compositions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.elemental_compositions_id_seq', 8, true);


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

SELECT pg_catalog.setval('public.ketcherails_common_templates_id_seq', 1, false);


--
-- Name: ketcherails_custom_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ketcherails_custom_templates_id_seq', 1, false);


--
-- Name: ketcherails_template_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ketcherails_template_categories_id_seq', 1, false);


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

SELECT pg_catalog.setval('public.matrices_id_seq', 15, true);


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

SELECT pg_catalog.setval('public.pg_search_documents_id_seq', 10, true);


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

SELECT pg_catalog.setval('public.reactions_id_seq', 1, true);


--
-- Name: reactions_samples_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reactions_samples_id_seq', 3, true);


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

SELECT pg_catalog.setval('public.samples_id_seq', 4, true);


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
-- Name: index_molecules_on_inchikey_and_is_partial; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX index_molecules_on_inchikey_and_is_partial ON public.molecules USING btree (inchikey, is_partial);


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
-- Name: matrices update_users_matrix_trg; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_users_matrix_trg AFTER INSERT OR UPDATE ON public.matrices FOR EACH ROW EXECUTE FUNCTION public.update_users_matrix();


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

