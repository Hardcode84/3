# SPDX-License-Identifier: Apache-2.0
"""Tests for sort_cmake_lists.py."""

import textwrap
from pathlib import Path

from sort_cmake_lists import process_file


def _run(tmp_path: Path, content: str) -> tuple[bool, str]:
    """Write *content* to a temp file, process it, return (changed, result)."""
    p = tmp_path / "CMakeLists.txt"
    p.write_text(textwrap.dedent(content))
    changed = process_file(p)
    return changed, p.read_text()


def test_sorts_source_files(tmp_path):
    changed, result = _run(
        tmp_path,
        """\
        add_library(MyLib
          Zebra.cpp
          Alpha.cpp
          Mid.cpp
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        add_library(MyLib
          Alpha.cpp
          Mid.cpp
          Zebra.cpp
        )
    """
    )


def test_sorts_link_libs(tmp_path):
    changed, result = _run(
        tmp_path,
        """\
        add_mlir_dialect_library(MLIRFoo
          A.cpp

          LINK_LIBS PUBLIC
          MLIRIR
          MLIRArith
          MLIRFunc
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        add_mlir_dialect_library(MLIRFoo
          A.cpp

          LINK_LIBS PUBLIC
          MLIRArith
          MLIRFunc
          MLIRIR
        )
    """
    )


def test_already_sorted_is_noop(tmp_path):
    changed, _ = _run(
        tmp_path,
        """\
        add_library(MyLib
          A.cpp
          B.cpp
          C.cpp
        )
        """,
    )
    assert not changed


def test_preserves_keywords_and_structure(tmp_path):
    changed, result = _run(
        tmp_path,
        """\
        add_mlir_dialect_library(MLIRFoo
          B.cpp
          A.cpp

          ADDITIONAL_HEADER_DIRS
          ${PROJECT_SOURCE_DIR}/include

          DEPENDS
          MLIRFooIncGen

          LINK_LIBS PUBLIC
          MLIRBar
          MLIRAlpha
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        add_mlir_dialect_library(MLIRFoo
          A.cpp
          B.cpp

          ADDITIONAL_HEADER_DIRS
          ${PROJECT_SOURCE_DIR}/include

          DEPENDS
          MLIRFooIncGen

          LINK_LIBS PUBLIC
          MLIRAlpha
          MLIRBar
        )
    """
    )


def test_does_not_sort_variables(tmp_path):
    """Variables like ${foo} should not be reordered."""
    changed, _ = _run(
        tmp_path,
        """\
        set(LIBS
          ${dialect_libs}
          ${conversion_libs}
          Alpha
          Beta
        )
        """,
    )
    assert not changed


def test_cmake_sort_off_guard(tmp_path):
    changed, result = _run(
        tmp_path,
        """\
        # cmake-sort: off
        add_library(MyLib
          Zebra.cpp
          Alpha.cpp
        )
        # cmake-sort: on
        """,
    )
    assert not changed


def test_set_command(tmp_path):
    changed, result = _run(
        tmp_path,
        """\
        set(LIBS
          Charlie
          Alpha
          Beta
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        set(LIBS
          Alpha
          Beta
          Charlie
        )
    """
    )


def test_case_insensitive_sort(tmp_path):
    """MLIRRewrite should come before MLIRROCDLTarget."""
    changed, result = _run(
        tmp_path,
        """\
        add_library(Foo
          MLIRROCDLTarget
          MLIRRewrite
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        add_library(Foo
          MLIRRewrite
          MLIRROCDLTarget
        )
    """
    )


def test_non_sortable_command_untouched(tmp_path):
    """Commands not in the sortable list should be left alone."""
    changed, _ = _run(
        tmp_path,
        """\
        install(TARGETS foo
          LIBRARY DESTINATION lib
          ARCHIVE DESTINATION lib
        )
        """,
    )
    assert not changed


def test_comments_break_blocks(tmp_path):
    """Comments within a list should act as separators."""
    changed, result = _run(
        tmp_path,
        """\
        add_library(Foo
          B.cpp
          A.cpp
          # Section two.
          D.cpp
          C.cpp
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        add_library(Foo
          A.cpp
          B.cpp
          # Section two.
          C.cpp
          D.cpp
        )
    """
    )


def test_cache_keyword_preserves_position(tmp_path):
    """CACHE STRING should stay in place, not get sorted into the value list."""
    changed, result = _run(
        tmp_path,
        """\
        set(LLVM_DISTRIBUTIONS
          Toolchain
          Development
          CACHE STRING "")
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        set(LLVM_DISTRIBUTIONS
          Development
          Toolchain
          CACHE STRING "")
    """
    )


def test_interface_keyword_is_separator(tmp_path):
    """INTERFACE should act as a block separator, libs after it get sorted."""
    changed, result = _run(
        tmp_path,
        """\
        target_link_libraries(
          my_target
          INTERFACE
            iree::foo
            iree::bar
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        target_link_libraries(
          my_target
          INTERFACE
            iree::bar
            iree::foo
        )
    """
    )


def test_bracket_argument_skipped(tmp_path):
    """set() with bracket arguments should not be sorted."""
    content = textwrap.dedent(
        """\
        set(_TEMPLATE [=[
        static void Foo() {
          Bar();
          Alpha();
        }
        ]=])
    """
    )
    changed, _ = _run(tmp_path, content)
    assert not changed


def test_target_link_libraries_private(tmp_path):
    """target_link_libraries with PRIVATE sorts only after the keyword."""
    changed, result = _run(
        tmp_path,
        """\
        target_link_libraries(my_target
          PRIVATE
          iree_runtime
          iree_hal
          iree_base
        )
        """,
    )
    assert changed
    assert result == textwrap.dedent(
        """\
        target_link_libraries(my_target
          PRIVATE
          iree_base
          iree_hal
          iree_runtime
        )
    """
    )
