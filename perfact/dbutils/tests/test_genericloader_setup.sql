CREATE TABLE testlc (
    testlc_id serial PRIMARY KEY, 
    testlc_author varchar,
    testlc_modtime timestamp default current_timestamp,
    testlc_name varchar
);

create view testlc_sel as 
select
    testlc_id as id,
    testlc_name as name
from testlc
;

create view from_testlc_sel as 
select
    testlc_id as id,
    testlc_name as name
from testlc
;

create view to_testlc_sel as 
select
    testlc_id as id,
    testlc_name as name
from testlc
;

CREATE TABLE testlct (
    testlct_id serial PRIMARY KEY,
    testlct_author varchar,
    testlct_modtime timestamp default current_timestamp,
    testlct_name varchar,
    testlct_from_testlc_id bigint references testlc(testlc_id),
    testlct_to_testlc_id bigint references testlc(testlc_id),
    testlct_testlc_id bigint references testlc(testlc_id)
);

create view testlct_sel as 
select
    testlct_id as id,
    testlct_name as name
from testlct
;

create or replace function db_username() 
returns text as 
$$ 
  begin 
    return 'test_user';
  end;
$$ language plpgsql;