from typing import Any, Callable, Optional, Protocol, TypedDict

from .conn import Executor


class User:
    """
    Class for the user object within the Context object

    :param name: Name of the user
    :param user_roles: List of active user roles
    :param is_manager: Pointer to the function is_manager
    :param user_has_role: Pointer to the function is_manager user_has_role

    """

    def __init__(
        self,
        name: str,
        user_roles: list[str],
        is_manager: Callable[[], bool],
        user_has_role: Callable[[list[str]], bool],
    ):
        self.name = name
        self.user_roles = user_roles
        self.is_manager = is_manager
        self.user_has_role = user_has_role


class CodedHook(Protocol):
    """
    Class describing the expected signature of the coded hooks.

    :param conn: DB Connector
    :type conn: Executor

    :param lib: Pointer to the lib functions
    :type lib: Any

    :param user: User object
    :type user: User

    :param id: Id of the record
    :type id: int

    :param table: Name of the table
    :type table: str
    """

    def __call__(self, conn: Executor, id: int, table: str, **kw: Any): ...


class MayResult(TypedDict):
    """The MayResult dict may be returned by may hooks"""

    may: bool
    """True if the lc transition is allowed. Otherwise false."""
    hint: str
    """May contain a hint for the user why the transition is not allowed."""


class MayHook(Protocol):
    """
    Class describing the expected signature of the may hooks. A may hook
    function must have the following signature:

    :param conn: DB Connector
    :type conn: Executor

    :param lib: Pointer to the lib functions
    :type lib: Any

    :param user: User object
    :type user: User

    :param id: Id of the record
    :type id: int

    :param table: Name of the table
    :type table: str

    :return: Returns true if the lc transition is allowed. May also return a
        MayResult dict instead.
    :rtype: bool | MayResult
    """

    def __call__(
        self, conn: Executor, id: int, table: str, **kw
    ) -> bool | MayResult: ...


class CodedHooksResolver(Protocol):
    """
    Class describing the signature of the coded_hooks_resolver function. The
    coded hooks resolver function must have the following signature:

    :param table: Name of the table
    :type table: str

    :param src_lc_id: ID of the source lc
    :type src_lc_id: int

    :param tgt_lc_id: ID of the target lc
    :type tgt_lc_id: int

    :param hook_name: Name of the hook
    :type hook_name: str

    :param hook_path: Overwrites the automatically build path. Defaults to None
    :type hook_path: Optional[str]

    :return: Returns a callable if the hook could be resolved
    :rtype: CodedHook | MayHook | None
    """

    def __call__(
        self,
        table: str,
        src_lc_id: int,
        tgt_lc_id: int,
        hook_name: str,
        hook_path: Optional[str] = None,
    ) -> CodedHook | MayHook | None: ...


class LCC:
    """
    Class for the lcc object within the Context object

    :param coded_hooks_resolver: Pointer to the function that will be used to
        resolve the coded hooks.
    :param side_effect_resolver: Pointer to the function that will be used to
        resolve the side effects.
    """

    def __init__(
        self,
        coded_hooks_resolver: CodedHooksResolver,
        side_effect_resolver: Callable[[str], Callable],
    ):
        self.coded_hooks_resolver = coded_hooks_resolver
        self.side_effect_resolver = side_effect_resolver


class SelfilterGenerator(Protocol):
    """
    Class describing the signature of the coded_hooks_resolver function. The
    coded hooks resolver function must have the following signature:

    :param table: Name of the table
    :type table: str

    :param column: ID of the source lc
    :type column: int

    :param kw: Additonal keyword arguments
    :type kw: Any

    :return: Returns the selfilter for the given table and column
    :rtype: str
    """

    def __call__(
        self,
        table: str,
        column: int,
        **kw: Any,
    ) -> str: ...


class Context:
    """
    Class for the ctx object

    :param conn: DB connector
    :param user: User object, containing information about the current user
    :param lcc: LCC object, containing functions to resolve the lcc hooks
    :param lib: Pointer to the lib context
    :param api: Pointer to the api context
    :param selfilter_generator: Pointer to a function that can generate the
        selfilter for a table.
    """

    def __init__(
        self,
        conn: Executor,
        user: User,
        lcc: LCC,
        lib: Any,
        api: Any,
        selfilter_generator: SelfilterGenerator,
    ):
        self.conn = conn
        self.user = user
        self.lib = lib
        self.lcc = lcc
        self.api = api
        self.selfilter_generator = selfilter_generator
