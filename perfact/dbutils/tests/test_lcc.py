# test cases for crud module
from ..crud import create, read, update
from ..lcc import _lc_update, _get_lch_columns, get_lct_infos, \
    perform_transition, _get_side_effects, collect_hooks, \
    transition_with_hooks, trigger_lct_events, _appevt_trigger_hook
from ..conn import Connection as DBConnection, Namespace
from pytest_postgresql import factories
import pytest
from datetime import timedelta
from ..api import Context, LCC, User
import os


postgresql_proc = factories.postgresql_proc()


@pytest.fixture(scope="function")
def conn(postgresql):
    """
    Create records in test, testlc, testlct.
    """
    conn = DBConnection(postgresql)
    base = os.path.dirname(__file__)
    setup_file = os.path.join(base, "test_lcc_setup.sql")
    with open(setup_file, "r", encoding="utf-8") as f:
        sql = f.read()
        conn.execute(sql)
    testlc_data = [
        {
            'testlc_id': 1,
            'testlc_name': 'running',
        },
        {
            'testlc_id': 2,
            'testlc_name': 'stopped',
        },
        {
            'testlc_id': 3,
            'testlc_name': 'explosion',
        }
    ]
    for testlc_payload in testlc_data:
        create(
            conn=conn,
            table='testlc',
            payload=testlc_payload,
        )

    testlct_data = [
        {
            'testlct_id': 1,
            'testlct_from_testlc_id': 1,
            'testlct_to_testlc_id': 2,
            'testlct_name': 'Stop machine'
        },
        {
            'testlct_id': 2,
            'testlct_from_testlc_id': 2,
            'testlct_to_testlc_id': 1,
            'testlct_name': 'Start machine'
        },
        {
            'testlct_id': 3,
            'testlct_from_testlc_id': 1,
            'testlct_to_testlc_id': 3,
            'testlct_name': 'Machine explodes',
            'testlct_deleted': True,
        },
    ]

    for testlct_payload in testlct_data:
        create(
            conn=conn,
            table='testlct',
            payload=testlct_payload
        )

    create(
        conn=conn,
        table='test',
        payload={
            'test_name': 'Machine-1',
            'test_testlc_id': 1
        }
    )

    testlctase_data = [
        {
            'testlctase_id': 1,
            'testlctase_name': 'Turn of lights',
            'testlctase_path': 'turn/of/lights/execute',
        },
        {
            'testlctase_id': 2,
            'testlctase_name': 'Close windows',
            'testlctase_path': 'close/windows/execute',
        },
    ]
    for testlctase_payload in testlctase_data:
        create(
            conn=conn,
            table='testlctase',
            payload=testlctase_payload
        )

    testlctse_data = [
        {
            'testlctse_id': 1,
            'testlctse_testlct_id': 1,
            'testlctse_testlctase_id': 1,
            'testlctse_seqnum': 10,
            'testlctse_somedata': 'Hello World',
        },
        {
            'testlctse_id': 2,
            'testlctse_testlct_id': 1,
            'testlctse_testlctase_id': 2,
            'testlctse_seqnum': 20,
        },
    ]
    for testlctse_payload in testlctse_data:
        create(
            conn=conn,
            table='testlctse',
            payload=testlctse_payload
        )

    yield conn


@pytest.fixture(scope="function")
def ctx(conn):
    """
    Create records in test, testlc, testlct.
    """
    return Context(
        conn=conn,
        user=User(
            name='test',
            user_roles=[],
            user_has_role=None,
            is_manager=None,
        ),
        lib=None,
        lcc=LCC(
            coded_hooks_resolver=None,
            side_effect_resolver=None,
        ),
        api=None,
        selfilter_generator=None,
    )


def test_simple_lcupdate(conn):
    """
    Test the _lc_update function
    """
    _lc_update(
        conn=conn,
        table='test',
        refid=1,
        tgt_lc_id=2,
        lct_id=1
    )
    res = read(
        conn=conn,
        table='test',
        ident={
            'test_id': 1
        }
    )
    assert res[0]['test_testlc_id'] == 2
    res = read(
        conn=conn,
        table='testlch',
        ident={
            'testlch_test_id': 1
        }
    )
    assert res
    assert res[0]['testlch_test_id'] == 1
    assert res[0]['testlch_testlct_id'] == 1


def test_lcupdate_with_lch_columns(conn):
    """
    Test _lc_update while using the lch_columns param.
    """
    _lc_update(
        conn=conn,
        table='test',
        refid=1,
        tgt_lc_id=2,
        lct_id=1,
        lch_columns=['name'],
    )
    test_res = read(
        conn=conn,
        table='test',
        ident={
            'test_id': 1
        }
    )
    assert test_res[0]['test_testlc_id'] == 2
    testlch_res = read(
        conn=conn,
        table='testlch',
        ident={
            'testlch_test_id': 1
        }
    )
    assert testlch_res[0]['testlch_name'] == test_res[0]['test_name']


def test_lcupdate_with_set_lchtimespent(conn):
    """
    Test _lc_update while using the set_lchtimespent param.
    """
    # Test with no previous lch entry
    _lc_update(
        conn=conn,
        table='test',
        refid=1,
        tgt_lc_id=2,
        lct_id=1,
        set_lchtimespent=True
    )

    testlch_res = read(
        conn=conn,
        table='testlch',
        ident={
            'testlch_test_id': 1
        },
        orderby=[('testlch_createtime', 'desc')],
        limit=1,
    )
    assert not testlch_res[0]['testlch_lchtimespent']

    # Test if calculation is correct
    createtime = next(iter(
        conn.execute(query="select now() - interval '2 seconds' as ts").rows()
    )).ts
    update(
        conn=conn,
        table='testlch',
        ident={
            'testlch_id': testlch_res[0]['testlch_id']
        },
        payload={
            'testlch_createtime': createtime,
        }
    )
    _lc_update(
        conn=conn,
        table='test',
        refid=1,
        tgt_lc_id=2,
        lct_id=1,
        set_lchtimespent=True
    )
    testlch_res = read(
        conn=conn,
        table='testlch',
        ident={
            'testlch_test_id': 1
        },
        orderby=[('testlch_createtime', 'desc')],
        limit=1,
    )
    assert testlch_res[0]['testlch_lchtimespent'] >= timedelta(seconds=2)


def test_get_lch_columns(conn):
    """
    Test the _get_lch_columns function.
    """
    res = _get_lch_columns(conn=conn, table='test')
    assert len(res) == 1
    assert res[0] == 'name'


def test_get_lct_infos(conn):
    """
    Test the get_lct_info function
    """
    res = get_lct_infos(
        conn=conn,
        table='test',
        src_lc_id=1,
        tgt_lc_id=2,
    )
    assert res['testlct_id'] == 1

    res = get_lct_infos(
        conn=conn,
        table='test',
        src_lc_id=1,
        lct_id=1,
    )
    assert res['testlct_id'] == 1
    # lct_id overwrites tgt_lc_id
    res = get_lct_infos(
        conn=conn,
        table='test',
        src_lc_id=1,
        tgt_lc_id=1,
        lct_id=1,
    )
    assert res['testlct_id'] == 1
    # Test tgt_lc_id = src_lc_id
    res = get_lct_infos(
        conn=conn,
        table='test',
        src_lc_id=1,
        tgt_lc_id=1,
    )
    assert not res


def test_get_lct_info_exceptions(conn):
    """
    Test that the get_lct_info function raises exceptions properly
    """
    with pytest.raises(ValueError):
        get_lct_infos(
            conn=conn,
            table='test',
            src_lc_id=1,
            lct_id=100,
        )

    with pytest.raises(ValueError):
        get_lct_infos(
            conn=conn,
            table='test',
            src_lc_id=1,
            tgt_lc_id=100,
        )
    with pytest.raises(AssertionError):
        get_lct_infos(
            conn=conn,
            table='test',
            src_lc_id=1,
        )
    with pytest.raises(ValueError):
        get_lct_infos(
            conn=conn,
            table='test',
            src_lc_id=1,
            tgt_lc_id=3,
        )


def test_perform_transition(ctx):
    """
    Test the perform_transition function
    """
    conn = ctx.conn

    def may(id, **kw):
        return {
            'may': True,
            'hint': ''
        }

    def disabled(id, **kw):
        return False

    def generic_func(id, **kw):
        return

    may_funcs = [
        may,
        lambda id, **kw: not disabled(id=id, **kw)
    ]
    pre_funcs = [
        generic_func
    ]
    post_funcs = [
        generic_func,
    ]
    perform_transition(
        conn=ctx.conn,
        lib=ctx.lib,
        user=ctx.user,
        table='test',
        refid=1,
        tgt_lc_id=2,
        may=may_funcs,
        pre=pre_funcs,
        post=post_funcs,
    )
    res = read(
        conn=conn,
        table='test',
        ident={
            'test_id': 1
        }
    )[0]
    assert res['test_testlc_id'] == 2

    perform_transition(
        conn=ctx.conn,
        lib=ctx.lib,
        user=ctx.user,
        table='test',
        refid=1,
        tgt_lc_id=1,
        may=may_funcs,
        pre=pre_funcs,
        post=post_funcs,
        # Test kw args
        hello_world='Hello World',
        test_name='Overwrite param'
    )


def test_perform_transition_no_hooks(ctx):
    """
    Test perform_transition function with no hooks. Meaning no may, pre
    or post functions.
    """
    conn = ctx.conn
    perform_transition(
        conn=ctx.conn,
        lib=ctx.lib,
        user=ctx.user,
        table='test',
        refid=1,
        tgt_lc_id=2,
    )
    res = read(
        conn=conn,
        table='test',
        ident={
            'test_id': 1
        }
    )[0]
    assert res['test_testlc_id'] == 2


def test_perform_transition_deleted_lct(ctx):
    """
    Test perform_transition function with deleted lct
    """
    with pytest.raises(ValueError):
        perform_transition(
            conn=ctx.conn,
            lib=ctx.lib,
            user=ctx.user,
            table='test',
            refid=1,
            tgt_lc_id=3,
        )


def test_perform_transition_no_transition(ctx):
    """
    Test perform_transition function when src_lc_id and tgt_lc_id are the same
    """
    counter = 0

    def generic_func(id, **kw):
        nonlocal counter
        counter += 1
        return True
    generic_func(id=1)

    perform_transition(
        conn=ctx.conn,
        lib=ctx.lib,
        user=ctx.user,
        table='test',
        refid=1,
        tgt_lc_id=1,
        may=[generic_func],
        pre=[generic_func],
        post=[generic_func],
    )
    assert counter == 1


def test_perform_transition_not_allowed(ctx):
    """
    Test perform_transition function with transition that is not allowed by may
    functions.
    """
    def may(id, **kw):
        return {
            'may': False,
            'hint': ''
        }
    with pytest.raises(AssertionError):
        perform_transition(
            conn=ctx.conn,
            lib=ctx.lib,
            user=ctx.user,
            table='test',
            refid=1,
            tgt_lc_id=2,
            may=[may],
        )

    def disabled(id, **kw):
        return True

    with pytest.raises(AssertionError):
        perform_transition(
            conn=ctx.conn,
            lib=ctx.lib,
            user=ctx.user,
            table='test',
            refid=1,
            tgt_lc_id=2,
            may=[lambda id, **kw: not disabled(id=id, **kw)],
        )

    def may_wrong_rettype(id, **kw):
        return 'Hello World'

    with pytest.raises(ValueError):
        perform_transition(
            conn=ctx.conn,
            lib=ctx.lib,
            user=ctx.user,
            table='test',
            refid=1,
            tgt_lc_id=2,
            may=[may_wrong_rettype],
        )

    ctx.conn.execute("""
        create or replace function prevent_inserts()
        returns trigger language plpgsql as $function$
        begin
          return null;
        end;
        $function$;
        create trigger prevent_inserts before insert on testlch
          for each row execute function prevent_inserts();
    """)
    with pytest.raises(AssertionError):
        perform_transition(
            conn=ctx.conn,
            lib=ctx.lib,
            user=ctx.user,
            table='test',
            refid=1,
            tgt_lc_id=2,
        )


def test_get_side_effects(conn):
    """
    Test the _get_side_effects function.
    """
    def turn_of_lights(id, **kw):
        return 'turn_of_lights'

    def close_windows(id, **kw):
        return 'close_windows'

    def side_effect_resolver_func(path):
        if path == 'turn/of/lights/execute':
            return turn_of_lights
        if path == 'close/windows/execute':
            return close_windows

    side_effect_resolver_func('no_path')  # for full coverage

    res = _get_side_effects(
        conn=conn,
        table='test',
        lct_id=1,
        side_effect_resolver=side_effect_resolver_func,
    )
    assert len(res) == 2
    assert res[0](id=1, some_key_word='Hello World') == 'turn_of_lights'
    assert res[1](id=1, some_key_word='Hello World') == 'close_windows'


def test_get_side_effects_no_sideeffect_table(conn):
    """
    Test the _get_side_effects function for a table that has no sideeffects
    """
    def dummy(id, **kw):
        return None

    def side_effect_resolver_func(path):
        return dummy

    dummy(id=1)  # for full coverage
    side_effect_resolver_func('no_path')  # for full coverage

    res = _get_side_effects(
        conn=conn,
        table='testlct',
        lct_id=1,
        side_effect_resolver=side_effect_resolver_func
    )
    assert not res


def test_get_side_effects_no_sideeffects_configured(conn):
    """
    Test the _get_side_effects function for an lct that has no sideeffects
    configured.
    """
    def dummy(id, **kw):
        return None

    def side_effect_resolver_func(path):
        return dummy

    dummy(id=1)  # for full coverage
    side_effect_resolver_func('no_path')  # for full coverage

    res = _get_side_effects(
        conn=conn,
        table='test',
        lct_id=2,
        side_effect_resolver=side_effect_resolver_func,
    )
    assert not res


def test_collect_hooks(conn):
    """
    Test the collect_hooks function.
    """
    def may(id, **kw):
        return True

    def disabled(id, **kw):
        return True

    def bl(id, **kw):
        return 'bl'

    def after_bl_hook(id, **kw):
        return 'after_bl_hook'

    def turn_of_lights(id, testlctse_id, **kw):
        assert testlctse_id
        return 'turn_of_lights'

    def close_windows(id, testlctse_id, **kw):
        assert testlctse_id
        return 'close_windows'

    def after_transition_hook(id, **kw):
        return 'after_transition_hook'

    def side_effect_resolver_func(path):
        if path == 'turn/of/lights/execute':
            return turn_of_lights
        if path == 'close/windows/execute':
            return close_windows
        return None

    def coded_hooks_resolver(
            table, src_lc_id, tgt_lc_id, hook_name, hook_path=None
    ):
        path = f'{table}/{src_lc_id}/{tgt_lc_id}/{hook_name}'
        if path == 'test/1/2/may':
            return may
        if path == 'test/1/2/disabled':
            return disabled
        if path == 'test/1/2/bl':
            return bl
        if path == 'test/1/2/after_bl_hook':
            return after_bl_hook
        if path == 'test/1/2/after_transition_hook':
            return after_transition_hook
        return None

    executed_trigger_func = False

    def trigger_func(conn, progname, payload, lib):
        nonlocal executed_trigger_func
        executed_trigger_func = True

    ctx = Context(
        conn=conn,
        user=Namespace(
            name='test',
        ),
        lib=Namespace(
            app=Namespace(
                appevt=Namespace(
                    trigger=Namespace(
                        execute=trigger_func
                    )
                )
            )
        ),
        lcc=None,
        api=None,
        selfilter_generator=None,
    )

    side_effect_resolver_func('no_path')  # for full coverage test
    coded_hooks_resolver(
        table='test',
        src_lc_id=1,
        tgt_lc_id=2,
        hook_name='no_path',
        hook_path=None,
    )  # for full coverage test
    res = collect_hooks(
        conn=conn,
        table='test',
        coded_hooks_resolver=coded_hooks_resolver,
        side_effect_resolver=side_effect_resolver_func,
        src_lc_id=1,
        tgt_lc_id=2,
        lct_id=1,
        coded=True,
        lib=ctx.lib,
        username=ctx.user.name
    )
    args = {
        'id': 1,
        'conn': ctx.conn,
        'lib': ctx.lib,
        'user': ctx.user,
        'table': 'test',
    }
    assert len(res['may']) == 2
    assert len(res['pre']) == 2
    assert len(res['post']) == 4
    assert res['may'][0](**args)
    assert not res['may'][1](**args)
    assert res['pre'][0](**args) == 'bl'
    assert res['pre'][1](**args) == 'after_bl_hook'
    assert res['post'][0](**args) == 'turn_of_lights'
    assert res['post'][1](**args) == 'close_windows'
    assert res['post'][2](**args) == 'after_transition_hook'
    res['post'][3](
        testlct_from_testlc_id=1,
        testlct_to_testlc_id=2,
        **args
    )
    assert executed_trigger_func

    res = collect_hooks(
        conn=conn,
        table='test',
        coded_hooks_resolver=coded_hooks_resolver,
        side_effect_resolver=side_effect_resolver_func,
        src_lc_id=1,
        tgt_lc_id=2,
        lct_id=1,
        coded=False,
        lib=ctx.lib,
        username=ctx.user.name
    )


def test_collect_hooks_no_coded_hooks(conn):
    """
    Test the collect_hooks function when no hooks can be found.
    """
    def side_effect_resolver_func(path):
        return None

    def coded_hooks_resolver(
            table, src_lc_id, tgt_lc_id, hook_name, hook_path=None
    ):
        return None

    side_effect_resolver_func('no_path')  # for full coverage test
    # Test no hooks
    res = collect_hooks(
        conn=conn,
        table='test',
        coded_hooks_resolver=coded_hooks_resolver,
        side_effect_resolver=side_effect_resolver_func,
        src_lc_id=2,
        tgt_lc_id=1,
        lct_id=2,
        coded=True,
        lib=None,
        username='test'
    )
    assert not res['may']
    assert not res['pre']
    # AppEvt Trigger will always be in the post hooks
    assert len(res['post']) == 1


def test_collect_hooks_side_effect_wrong_config(conn):
    """
    Test the collect_hooks function when the path of a sideeffect can
    not be found.
    """
    def side_effect_resolver_func(path):
        return None

    def coded_hooks_resolver(
            table, src_lc_id, tgt_lc_id, hook_name, hook_path=None
    ):
        return None
    coded_hooks_resolver(
        table='test',
        src_lc_id=1,
        tgt_lc_id=2,
        hook_name='no_path'
    )  # full covergage

    with pytest.raises(ValueError):
        collect_hooks(
            conn=conn,
            table='test',
            coded_hooks_resolver=coded_hooks_resolver,
            side_effect_resolver=side_effect_resolver_func,
            src_lc_id=1,
            tgt_lc_id=2,
            lct_id=1,
            coded=True,
            lib=None,
            username='test'
        )


def test_collect_hooks_blpath(conn):
    """
    Test the collect_hooks function with overwritten blpath.
    """
    def custom_blpath(id, **kw):
        return 'custom_blpath'

    def side_effect_resolver_func(path):
        return None

    def coded_hooks_resolver(
            table, src_lc_id, tgt_lc_id, hook_name, hook_path=None
    ):
        if hook_path == 'my/very/special/path/execute':
            return custom_blpath
        return None

    side_effect_resolver_func('no_path')  # for full coverage test

    # Test no hooks
    res = collect_hooks(
        conn=conn,
        table='test',
        coded_hooks_resolver=coded_hooks_resolver,
        side_effect_resolver=side_effect_resolver_func,
        src_lc_id=2,
        tgt_lc_id=1,
        lct_id=2,
        blpath='my/very/special/path/execute',
        coded=True,
        lib=None,
        username='test'
    )
    assert not res['may']
    assert len(res['pre']) == 1
    # AppEvt Trigger hook
    assert len(res['post']) == 1
    assert res['pre'][0](id=1) == 'custom_blpath'


def test_transition_with_hooks(conn):
    """
    Test the function transition_with_hooks.
    """
    counter = 0

    def may(id, **kw):
        nonlocal counter
        counter += 1
        return True

    def disabled(id, **kw):
        nonlocal counter
        counter += 1
        return False

    def bl(id, **kw):
        nonlocal counter
        counter += 1
        return 'bl'

    def after_bl_hook(id, **kw):
        nonlocal counter
        counter += 1
        return 'after_bl_hook'

    def turn_of_lights(id, **kw):
        nonlocal counter
        counter += 1
        return 'turn_of_lights'

    def close_windows(id, **kw):
        nonlocal counter
        counter += 1
        return 'close_windows'

    def after_transition_hook(id, **kw):
        nonlocal counter
        counter += 1
        return 'after_transition_hook'

    def side_effect_resolver(path):
        if path == 'turn/of/lights/execute':
            return turn_of_lights
        if path == 'close/windows/execute':
            return close_windows
        return None

    def coded_hooks_resolver(
            table, src_lc_id, tgt_lc_id, hook_name, hook_path=None
    ):
        path = f'{table}/{src_lc_id}/{tgt_lc_id}/{hook_name}'
        if path == 'test/1/2/may':
            return may
        if path == 'test/1/2/disabled':
            return disabled
        if path == 'test/1/2/bl':
            return bl
        if path == 'test/1/2/after_bl_hook':
            return after_bl_hook
        if path == 'test/1/2/after_transition_hook':
            return after_transition_hook
        return None

    def evt_trigger_func(conn, progname, lib, payload=None):
        nonlocal counter
        counter += 1
        return 'evt_trigger_func'

    side_effect_resolver('no_path')  # for full coverage test
    coded_hooks_resolver(
        table='test',
        src_lc_id=1,
        tgt_lc_id=2,
        hook_name='no_path'
    )  # for full coverage test
    ctx = Context(
        conn=conn,
        user=Namespace(name='test'),
        lcc=Namespace(
            coded_hooks_resolver=coded_hooks_resolver,
            side_effect_resolver=side_effect_resolver,
        ),
        lib=Namespace(
            app=Namespace(
                appevt=Namespace(
                    trigger=Namespace(
                        execute=evt_trigger_func
                    )
                )
            )
        ),
        api=None,
        selfilter_generator=None,
    )

    transition_with_hooks(
        conn=ctx.conn,
        lib=ctx.lib,
        user=ctx.user,
        lcc=ctx.lcc,
        table='test',
        refid=1,
        tgt_lc_id=2,
    )
    # Must be 3 since we have 2 side effects and the appevt trigger hook
    assert counter == 3
    counter = 0
    # Set coded flag
    update(
        conn=conn,
        table='testlct',
        ident={
            'testlct_id': 1
        },
        payload={
            'testlct_coded': True
        }
    )
    # Reset lc of test record
    _lc_update(
        conn=conn,
        table='test',
        refid=1,
        tgt_lc_id=1,
        lct_id=2,
    )
    transition_with_hooks(
        conn=ctx.conn,
        lib=ctx.lib,
        user=ctx.user,
        lcc=ctx.lcc,
        table='test',
        refid=1,
        tgt_lc_id=2,
    )
    # 5 coded hooks + 2 side effects + 1 appevt trigger
    assert counter == 8

    transition_with_hooks(
        conn=ctx.conn,
        lib=ctx.lib,
        user=ctx.user,
        lcc=ctx.lcc,
        table='test',
        refid=1,
        tgt_lc_id=2,
    )
    assert counter == 8


def test_trigger_lct_events(conn):
    def trigger_func(conn, progname, payload, lib):
        nonlocal lct_evt_executed
        nonlocal progname_evt_executed
        if progname == 'testlct':
            lct_evt_executed = True
        if progname == 'test':
            progname_evt_executed = True

    ctx = Context(
        conn=conn,
        user=Namespace(name='test'),
        lib=Namespace(
            app=Namespace(
                appevt=Namespace(
                    trigger=Namespace(
                        execute=trigger_func
                    )
                )
            )
        ),
        lcc=None,
        api=None,
        selfilter_generator=None,
    )
    lct_evt_executed = False
    progname_evt_executed = False

    trigger_lct_events(
        conn=ctx.conn,
        lib=ctx.lib,
        username=ctx.user.name,
        table='test',
        refid=1,
        src_lc_id=1,
        tgt_lc_id=2,
        progname='test',
    )
    assert lct_evt_executed
    assert progname_evt_executed

    lct_evt_executed = False
    progname_evt_executed = False
    trigger_lct_events(
        conn=ctx.conn,
        lib=ctx.lib,
        username=ctx.user.name,
        table='test',
        refid=1,
        src_lc_id=1,
        tgt_lc_id=2,
        progname=None,
    )
    assert lct_evt_executed
    assert not progname_evt_executed


def test_appevt_trigger_hook_exceptions(ctx):
    with pytest.raises(ValueError):
        _appevt_trigger_hook(
            conn=ctx.conn,
            lib=ctx.lib,
            username=ctx.user.name,
            table='test',
            id=1,
            testlct_to_testlc_id=2,
        )
    with pytest.raises(ValueError):
        _appevt_trigger_hook(
            conn=ctx.conn,
            lib=ctx.lib,
            username=ctx.user.name,
            table='test',
            id=1,
            testlct_from_testlc_id=1,
        )
