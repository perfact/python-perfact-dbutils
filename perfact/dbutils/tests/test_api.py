from ..api import LCC, Context, User
from ..conn import Connection


def test_create_Context_obj():
    """
    Simple create of the context obj. Tests downwards compatibility.
    """
    ctx = Context(
        conn=Connection(conn=None),
        user=User(
            name="test",
            user_roles=[],
            is_manager=None,
            user_has_role=None,
        ),
        lcc=LCC(
            coded_hooks_resolver=None,
            side_effect_resolver=None,
        ),
        lib=None,
        api=None,
    )
    assert ctx.selfilter_generator(table="test", column="test_id") == ""

    def selfilter_gen(table, column):
        return "Hello World"

    ctx = Context(
        conn=Connection(conn=None),
        user=User(
            name="test",
            user_roles=[],
            is_manager=None,
            user_has_role=None,
        ),
        lcc=LCC(
            coded_hooks_resolver=None,
            side_effect_resolver=None,
        ),
        lib=None,
        api=None,
        selfilter_generator=selfilter_gen,
    )
    selfilter = ctx.selfilter_generator(table="test", column="test_id")
    assert selfilter == "Hello World"
