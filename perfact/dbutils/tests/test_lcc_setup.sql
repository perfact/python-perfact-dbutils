CREATE TABLE testlc (
    testlc_id serial PRIMARY KEY, 
    testlc_author varchar,
    testlc_modtime timestamp default current_timestamp,
    testlc_name varchar
);

CREATE TABLE testlct (
    testlct_id serial PRIMARY KEY,
    testlct_author varchar,
    testlct_modtime timestamp default current_timestamp,
    testlct_name varchar,
    testlct_blpath varchar,
    testlct_deleted boolean default false,
    testlct_coded boolean default false,
    testlct_from_testlc_id bigint references testlc(testlc_id),
    testlct_to_testlc_id bigint references testlc(testlc_id)
);

CREATE TABLE test (
    test_id serial PRIMARY KEY,
    test_author varchar,
    test_modtime timestamp default current_timestamp,
    test_name varchar,
    test_testlc_id bigint references testlc(testlc_id)
);

CREATE TABLE testlch (
    testlch_id serial PRIMARY KEY,
    testlch_author varchar,
    testlch_modtime timestamp with time zone default current_timestamp,
    testlch_createtime timestamp with time zone default current_timestamp,
    testlch_testlct_id bigint references testlct(testlct_id),
    testlch_test_id bigint references test(test_id),
    testlch_lchtimespent interval,
    testlch_name varchar
);

CREATE TABLE testlctase (
    testlctase_id serial PRIMARY KEY,
    testlctase_author varchar,
    testlctase_modtime timestamp with time zone default current_timestamp,
    testlctase_createtime timestamp with time zone default current_timestamp,
    testlctase_path text,
    testlctase_name varchar
);

CREATE TABLE testlctse (
    testlctse_id serial PRIMARY KEY,
    testlctse_author varchar,
    testlctse_modtime timestamp with time zone default current_timestamp,
    testlctse_createtime timestamp with time zone default current_timestamp,
    testlctse_testlct_id bigint references testlct(testlct_id),
    testlctse_testlctase_id bigint references testlctase(testlctase_id),
    testlctse_seqnum integer,
    testlctse_somedata varchar
);

create or replace function db_username() 
returns text as 
$$ 
  begin 
    return 'test_user';
  end;
$$ language plpgsql;