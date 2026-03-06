from __future__ import annotations

from functools import partial
from typing import Any, Callable, Mapping, Optional, TypedDict

from psycopg2 import sql

from .api import LCC, CodedHook, CodedHooksResolver, MayHook, User
from .conn import Executor
from .crud import create, read, update
from .schemainfo import get_columns


def _lc_update(
    conn: Executor,
    table: str,
    refid: int,
    tgt_lc_id: int,
    lct_id: int,
    lch_columns: Optional[list[str]] = None,
    set_lchtimespent: bool = False,
) -> Mapping[str, Any] | None:
    """
    Update the lc of the the given record.

    :param conn: Connection object to database where the lc update should be
        performed.
    :param table: Name of the table in the database
    :param refid: Id of the record in the given table
    :param tgt_lc_id: Target lc_id
    :param lct_id: ID of the lct that will be performed with this update
    :param lch_columns: List of columns that exists in the source table and the
        lch-table. The column names must be given without the table prefix.
        Defaults to None.
    :param set_lchtimespent: If true, calculates the timespent in an lc and
        sets it in the lch-table. If this param is true, the lch-table must
        have a column named "<lch-table>_lchtimespent".

    :returns: Returns the data of the created lch entry. Returns None if no
        entry was created in the lch table.
    """
    ident = {
        f"{table}_id": refid,
    }
    lc_table = f"{table}lc"
    update(
        conn=conn,
        table=table,
        ident=ident,
        payload={
            f"{table}_{lc_table}_id": tgt_lc_id,
        },
    )

    ref_res = read(
        conn=conn,
        table=table,
        ident=ident,
    )[0]

    lch_table = f"{table}lch"

    lch_payload = {
        f"{lch_table}_{table}_id": refid,
        f"{lch_table}_{table}lct_id": lct_id,
    }
    if lch_columns:
        for column in lch_columns:
            lch_payload[f"{lch_table}_{column}"] = ref_res[f"{table}_{column}"]

    if set_lchtimespent:
        last_lchrecord = read(
            conn=conn,
            table=lch_table,
            columns=[f"{lch_table}_createtime"],
            ident={
                f"{lch_table}_{table}_id": refid,
            },
            orderby=[(f"{lch_table}_id", "desc")],
            limit=1,
        )
        if last_lchrecord:
            now = next(iter(conn.execute(query="select now() as now").rows())).now
            lch_payload[f"{lch_table}_lchtimespent"] = (
                now - last_lchrecord[0][f"{lch_table}_createtime"]
            )

    return create(
        conn=conn,
        table=lch_table,
        payload=lch_payload,
    )


def _get_lch_columns(conn: Executor, table: str) -> list[str]:
    """Get columns that exists in the given table and its corresponding lch
    table. This function is for example used when performing an lc update.

    :param conn: Connection object to database
    :param table: Name of the table in the database
    :return: Returns a list of columns that exists in both tables. The column
        names are listed without the table prefix.
    """
    table_cols = set(get_columns(conn=conn, table=table, full_colname=False))
    lch_cols = set(get_columns(conn=conn, table=f"{table}lch", full_colname=False))
    excludes = {
        "id",
        "createtime",
        "creator",
        "modtime",
        "author",
        f"{table}_id",
        f"{table}lct_id",
    }
    result = table_cols & lch_cols
    result -= excludes
    return list(result)


def get_lct_infos(
    conn: Executor,
    table: str,
    src_lc_id: int,
    tgt_lc_id: Optional[int] = None,
    lct_id: Optional[int] = None,
) -> Mapping[str, Any] | None:
    """Check if the given lct_id or tgt_lc_id is valid for the given refid.
    Returns the data of the resolved lct.

    :param conn: Connection object to database
    :param table: Name of the table
    :param src_lc_id: ID of the src lc
    :param tgt_lc_id: ID of the target lc. Either tgt_lc_id or lct_id must be
        given. If both given, lct_id overwrites tgt_lc_id. Defaults to None.
    :param lct_id: ID of the lct that should be performed. Either tgt_lc_id or
        lct_id must be given. If both given, lct_id overwrites tgt_lc_id.
        Defaults to None.

    :return: Returns the data of the lct record. Returns None if the src lc id
        is equal to the tgt lc id.
    :raise: Raises a ValueError if the lct could not be resolved
    """
    lct_table = f"{table}lct"
    lc_table = f"{table}lc"

    if not (tgt_lc_id or lct_id):
        raise AssertionError("Target lc_id or lct_id must be given")

    if lct_id:
        lct_res = read(
            conn=conn,
            table=lct_table,
            ident={
                f"{lct_table}_id": lct_id,
            },
        )
        if not lct_res:
            raise ValueError("Given lct_id does not exist")
        tgt_lc_id = lct_res[0][f"{lct_table}_to_{lc_table}_id"]

    if src_lc_id == tgt_lc_id:
        return None

    lct_res = read(
        conn=conn,
        table=lct_table,
        ident={
            f"{lct_table}_from_{lc_table}_id": src_lc_id,
            f"{lct_table}_to_{lc_table}_id": tgt_lc_id,
        },
    )
    if not lct_res:
        raise ValueError("LC Transition does not exist")

    if lct_res[0].get(f"{table}lct_deleted"):
        raise ValueError("Transition is deleted")

    return lct_res[0]


def perform_transition(
    conn: Executor,
    table: str,
    refid: int,
    tgt_lc_id: Optional[int] = None,
    lct_id: Optional[int] = None,
    may: Optional[list[MayHook]] = None,
    pre: Optional[list[CodedHook]] = None,
    post: Optional[list[CodedHook]] = None,
    **kw: Any,
) -> Mapping[str, Any] | None:
    """Perform an lc transition. Before performing the actual transition, this
    function will check if the desired lc transition may be performed.
    If the transition is allowed the function will do the following actions:

    1. Execute pre scripts if given
    2. Update lc and create lch entry
    3. Execute post scripts if given

    :param conn: Database connector
    :param table: Name of the table
    :param refid: ID of the record that will be transitioned into the next lc
    :param tgt_lc_id: ID of the target lc. Either tgt_lc_id or lct_id must be
        given. If both given, lct_id overwrites tgt_lc_id. Defaults to None.
    :param lct_id: ID of the lct that should be performed. Either tgt_lc_id or
        lct_id must be given. If both given, lct_id overwrites tgt_lc_id.
        Defaults to None.
    :param may: List of may functions which will be checked before performing
        the transition. These must either return a boolean or a dict containing
        the key "may" which must have a boolean value. The functions will
        receive the following additional data: the values of the ref record and
        the values of the performed lct. Defaults to None.
    :param pre: List of functions that will be executed before performing the
        actual transition. The functions will receive the following additional
        data: the values of the ref record and the values of the performed lct.
        Defaults to None.
    :param post: List of functions that will be executed before performing the
        actual transition. It is possible to pass a function as a tuple of the
        callable the function and additional data (for example sideeffects).
        The functions will receive the following additional data: the values of
        each column of the ref record, the values of the performed lct, the
        values of the created lch entry. Defaults to None.
    :param kw: Additional keyword arguments that will be passed to the may,
        pre and post functions.

    :returns: Returns the data of the created lch entry or None, if no
        tranition was performed.
    """
    ref_data = dict(
        read(
            conn=conn,
            table=table,
            ident={
                f"{table}_id": refid,
            },
        )[0]
    )
    src_lc_id = ref_data[f"{table}_{table}lc_id"]
    ref_data.update(kw)

    lct_data = get_lct_infos(
        conn=conn,
        table=table,
        src_lc_id=src_lc_id,
        tgt_lc_id=tgt_lc_id,
        lct_id=lct_id,
    )
    # Do nothing if we don't have any lct_data. This is the case if src_lc_id
    # and tgt_lc_id is the same.
    if not lct_data:
        return None
    ref_data.update(lct_data)

    tgt_lc_id = lct_data[f"{table}lct_to_{table}lc_id"]
    lct_id = lct_data[f"{table}lct_id"]

    if may:
        for may_cond in may:
            res = may_cond(conn=conn, table=table, id=refid, **ref_data)
            if isinstance(res, bool):
                if not res:
                    raise AssertionError("Not allowed")
            elif isinstance(res, dict):
                if not res["may"]:
                    raise AssertionError("Not allowed")
            else:
                raise ValueError("May result not supported")

    if pre:
        for pre_func in pre:
            pre_func(conn=conn, table=table, id=refid, **ref_data)

    lch_cols = get_columns(
        conn=conn,
        table=f"{table}lch",
        full_colname=False,
    )
    has_lchtimespent = "lchtimespent" in lch_cols
    lch_data = _lc_update(
        conn=conn,
        table=table,
        refid=refid,
        tgt_lc_id=tgt_lc_id,
        lct_id=lct_id,
        lch_columns=_get_lch_columns(conn=conn, table=table),
        set_lchtimespent=has_lchtimespent,
    )
    if not lch_data:
        raise AssertionError("LCH data not created")

    if post:
        post_data = ref_data | dict(lch_data)
        for post_func in post:
            post_func(conn=conn, table=table, id=refid, **post_data)

    return lch_data


def _get_side_effects(
    conn: Executor,
    table: str,
    lct_id: int,
    side_effect_resolver: Callable[[str], Callable | None],
) -> list[Callable] | None:
    """Get the configured side effects for an lct. Returns None if the given
    table has no side effects table (lctse) or if no side effects are
    configured for the given lct.

    :param conn: Connection object to database
    :param table: Name of the table
    :param lct_id: ID of the lct
    :param side_effect_resolver: Pointer to a function that receives a string
        (path) and returns a callable. Used to resolve side effects.
    :return: Returns a list of side effects or None. Each sideeffect will be
        represented by a tuple containing the path and additional data.
    :raises: Raises a ValueError if a side effect misconfiguration was found.
    """
    query = """--sql
        select
          exists (
            select 1
            from pg_tables
            where tablename = %(table_lctse)s
          ) as has_sideeffects
    """
    payload: Mapping[str, Any] = {"table_lctse": f"{table}lctse"}
    res = conn.execute(query=query, **payload)
    has_sideeffects = next(iter(res.rows())).has_sideeffects
    if not has_sideeffects:
        return None

    table_lctse = f"{table}lctse"
    table_lctase = f"{table}lctase"
    lctse_query = sql.SQL("""--sql
        select
          {lctase_path} as path,
          {lctse}.*
        from {lctase}
        join {lctse}
          on {lctse_lctase_id} = {lctase_id}
        where {lctse_lct_id} = {lct_id}
        order by {lctse_seqnum}
    """).format(
        lctase_path=sql.Identifier(f"{table_lctase}_path"),
        lctse=sql.Identifier(table_lctse),
        lctase=sql.Identifier(table_lctase),
        lctse_lctase_id=sql.Identifier(f"{table_lctse}_{table_lctase}_id"),
        lctase_id=sql.Identifier(f"{table_lctase}_id"),
        lctse_lct_id=sql.Identifier(f"{table_lctse}_{table}lct_id"),
        lctse_seqnum=sql.Identifier(f"{table_lctse}_seqnum"),
        lct_id=sql.Placeholder("lct_id"),
    )
    lctse_payload: Mapping[str, Any] = {"lct_id": lct_id}
    res = conn.execute(
        query=lctse_query,
        **lctse_payload,
    )
    if not res.tuples:
        return None
    rows = list(res.dicts())
    result: list[Callable] = []
    for row in rows:
        path = row.pop("path")
        base_func = side_effect_resolver(path)
        if not base_func:
            raise ValueError("Side effect misconfiguration found!")
        side_effect_with_data_func = partial(base_func, **row)
        result.append(side_effect_with_data_func)
    return result


def _appevt_trigger_hook(
    conn: Executor,
    lib: Any,
    username: str,
    id: int,
    table: str,
    **kw: Any,
):
    """
    Wrapper for the trigger_lct_events function which can be called as a hook
    in perform_transition.

    :param conn: Database connector
    :param username: Name of the user
    :param lib: Pointer to the lib context containing the lib functions
    :param table: Name of the table
    :param id: ID of the record in the table
    """
    src_lc_id = kw.get(f"{table}lct_from_{table}lc_id")
    tgt_lc_id = kw.get(f"{table}lct_to_{table}lc_id")
    progname = kw.get(f"{table}lct_progname")

    if not src_lc_id:
        raise ValueError("Missing src lc id")
    if not tgt_lc_id:
        raise ValueError("Missing tgt lc id")

    trigger_lct_events(
        conn=conn,
        lib=lib,
        username=username,
        table=table,
        refid=id,
        src_lc_id=int(src_lc_id),
        tgt_lc_id=int(tgt_lc_id),
        progname=str(progname) if progname else None,
    )


def collect_hooks(
    conn: Executor,
    table: str,
    coded_hooks_resolver: CodedHooksResolver,
    side_effect_resolver: Callable[[str], Callable | None],
    src_lc_id: int,
    tgt_lc_id: int,
    lct_id: int,
    coded: bool,
    username: str,
    lib: Any,
    blpath: Optional[str] = None,
) -> Mapping[str, list[MayHook | CodedHook]]:
    """Collect coded hooks for the given lct.

    :param conn: Connection object to database
    :param table: Name of the table
    :param coded_hooks_resolver: Pointer to a function that must have the
        following signature: table, src_lc_id, tgt_lc_id, hook_name,
        hook_path=None. Used to resolve coded hooks.
    :param side_effect_resolver: Pointer to a function that receives a string
        (path) and returns a callable. Used to resolve side effects.
    :param src_lc_id: ID of the source lc
    :param tgt_lc_id: ID of the target lc
    :param lct_id: ID of the lct
    :param coded: If the lct is coded, retrieve codes hooks and add them to the
        list of may, pre, post hooks.
    :param username: Name of the user
    :param lib: Pointer to the lib context containing the lib functions
    :param blpath: Overwrites path to bl script
    :return: Returns a dictionary containing the following keys: may, pre,
        post. Each field contains a list of hooks if hooks can be found.
    """
    result: Mapping[str, list[MayHook | CodedHook]] = {
        "may": [],
        "pre": [],
        "post": [],
    }

    # Always retrieve side effects
    side_effects = _get_side_effects(
        conn=conn,
        table=table,
        lct_id=lct_id,
        side_effect_resolver=side_effect_resolver,
    )
    if side_effects:
        result["post"].extend(side_effects)

    if not coded:
        result["post"].append(partial(_appevt_trigger_hook, lib=lib, username=username))
        return result

    # Retrieve coded hooks when coded is true
    class _CodedHookArgs(TypedDict):
        table: str
        src_lc_id: int
        tgt_lc_id: int

    args: _CodedHookArgs = {
        "table": table,
        "src_lc_id": src_lc_id,
        "tgt_lc_id": tgt_lc_id,
    }
    may_func = coded_hooks_resolver(hook_name="may", **args)
    if may_func:
        result["may"].append(may_func)

    disabled_func = coded_hooks_resolver(hook_name="disabled", **args)
    if disabled_func:

        def negate(func, **kw):
            return not func(**kw)

        result["may"].append(partial(negate, disabled_func))

    bl_func = coded_hooks_resolver(hook_name="bl", hook_path=blpath, **args)
    if bl_func:
        result["pre"].append(bl_func)

    after_bl_hook_func = coded_hooks_resolver(hook_name="after_bl_hook", **args)
    if after_bl_hook_func:
        result["pre"].append(after_bl_hook_func)

    after_transition_hook = coded_hooks_resolver(
        hook_name="after_transition_hook", **args
    )
    if after_transition_hook:
        result["post"].append(after_transition_hook)

    # Appevt trigger hook should always be the very last hook that will be
    # executed
    result["post"].append(partial(_appevt_trigger_hook, lib=lib, username=username))

    return result


def transition_with_hooks(
    conn: Executor,
    user: User,
    lcc: LCC,
    table: str,
    refid: int,
    lib: Any,
    tgt_lc_id: Optional[int] = None,
    lct_id: Optional[int] = None,
    **kw: Any,
) -> Mapping[str, Any] | None:
    """Perform an lc transition while respecting hooks (may, disabled, bl,
    bl_after_hook, after_transition_hook) and configured side effects.

    :param conn: Database connector
    :param user: User object containing information about the user
    :param lib: Pointer to the lib context containing the lib functions
    :param lcc: LCC object containing the lcc resolver functions
    :param table: Name of the table
    :param refid: ID of the record that will be transitioned
    :param tgt_lc_id: ID of the target lc. Either tgt_lc_id or lct_id
        must be given. Defaults to None.
    :param lct_id: ID of the lc transition. Either tgt_lc_id or lct_id
        must be given. Defaults to None.
    :param kw: Additional keyword arguments that will be passed to the may, pre
        and post functions.

    :returns: Returns the data of the performed lc transition. If no lc
        transition was performed, returns None.

    :raises: May raise ValueError or AssertionError if the given params or
        existing configurations are not valid.

    .. code-block:: python

        from perfact.dbutils.lcc import transition_with_hooks

        transition_with_hooks(
            conn=ctx.conn,
            lib=ctx.lib,
            user=ctx.user,
            lcc=ctx.lcc,
            table='test',
            refid=test_id,
            tgt_lc_id=2,
        )

    """
    data = read(
        conn=conn,
        table=table,
        ident={
            f"{table}_id": refid,
        },
    )[0]
    src_lc_id = data[f"{table}_{table}lc_id"]

    lct_info = get_lct_infos(
        conn=conn,
        table=table,
        src_lc_id=src_lc_id,
        tgt_lc_id=tgt_lc_id,
        lct_id=lct_id,
    )
    # Src and tgt lc_id is the same
    if not lct_info:
        return None
    tgt_lc_id = lct_info[f"{table}lct_to_{table}lc_id"]

    hooks = collect_hooks(
        conn=conn,
        table=table,
        coded_hooks_resolver=lcc.coded_hooks_resolver,
        side_effect_resolver=lcc.side_effect_resolver,
        src_lc_id=src_lc_id,
        tgt_lc_id=tgt_lc_id,
        lct_id=lct_info[f"{table}lct_id"],
        blpath=lct_info.get(f"{table}lct_blpath"),
        coded=lct_info[f"{table}lct_coded"],
        username=user.name,
        lib=lib,
    )
    may: list | None = hooks["may"]
    pre: list | None = hooks["pre"]
    post: list | None = hooks["post"]

    perform_transition(
        conn=conn,
        table=table,
        refid=refid,
        tgt_lc_id=tgt_lc_id,
        lct_id=None,
        may=may,
        pre=pre,
        post=post,
        **kw,
    )

    return lct_info


def trigger_lct_events(
    conn: Executor,
    lib: Any,
    username: str,
    table: str,
    refid: int,
    src_lc_id: int,
    tgt_lc_id: int,
    progname: Optional[str] = None,
):
    """
    Trigger lct events. Triggers a <table>lct event and if a progname is given,
    trigger the progname as an event.

    :param conn: Database connector
    :param username: Name of the user
    :param lib: Pointer to the lib context containing the lib functions
    :param table: Name of the table
    :param refid: ID of the record that was transitioned into the next lc
    :param src_lc_id: ID of the src lc
    :param tgt_lc_id: ID of the target lc
    :param progname: Progname of the lct. If given, trigger an event with the
        progname as the events name

    """
    # throw a generic event always
    payload = {
        f"{table}_id": refid,
        "lc_from_id": src_lc_id,
        "lc_to_id": tgt_lc_id,
        "author": username,
        "progname": progname,
    }
    lib.app.appevt.trigger.execute(
        conn=conn,
        progname=f"{table}lct",
        payload=payload,
        lib=lib,
    )

    # throw a named event if lct progname is set
    if progname:
        lib.app.appevt.trigger.execute(
            conn=conn,
            progname=progname,
            payload=payload,
            lib=lib,
        )
