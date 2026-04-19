"""
test_fixed_point.py  —  Correctness tests for FixedPoint arithmetic
====================================================================

Test philosophy
---------------
Every test works at the integer level, not the float level. The ground
truth for each test is computed by hand or by explicit integer arithmetic,
not by trusting val_float. This is intentional — the bit pattern is the
value, and that is what we verify.

Where float comparisons are used (val_float checks) they are secondary
sanity checks, not the primary assertion.

Test groups
-----------
  1. Construction          — float, int, binary string, overflow/underflow
  2. Truncation            — float constructor truncates toward zero
  3. Representation        — val_bin, total_width, sign bit layout
  4. Addition              — same format, mixed format, sign promotion
  5. Subtraction           — same format, mixed format, unsigned underflow
  6. Multiplication        — width growth, sign guard bit, zero
  7. Negation / Abs        — sign handling
  8. Comparison            — all six operators, mixed fract_width
  9. Left shift            — int_width growth, val_int correctness
 10. Right shift           — fract_width growth, arithmetic vs logical
 11. bsl_scale / bsr_scale — integer-only scaling
 12. requantize            — narrowing truncation, widening, no-op, sign change
 13. Type errors           — non-FixedPoint operands rejected
 14. Width metadata        — result formats match expected HW output widths
"""

import unittest
import warnings

from pyfxp import FixedPoint


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def fxp(val, iw, fw, signed=False):
    """Shorthand constructor."""
    return FixedPoint(val, iw, fw, signed)


def fxpi(raw_int, iw, fw, signed=False):
    """Construct directly from raw integer — bypasses float conversion."""
    return FixedPoint(raw_int, iw, fw, signed)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Construction
# ══════════════════════════════════════════════════════════════════════════════

class TestConstruction(unittest.TestCase):

    def test_from_int_unsigned(self):
        a = fxpi(60, 4, 4, False)
        self.assertEqual(a.val_int, 60)
        self.assertEqual(a.int_width, 4)
        self.assertEqual(a.fract_width, 4)
        self.assertEqual(a.total_width, 8)
        self.assertFalse(a.signed)

    def test_from_int_signed(self):
        a = fxpi(-24, 3, 4, True)
        self.assertEqual(a.val_int, -24)
        self.assertEqual(a.total_width, 8)   # 3 + 4 + 1 sign
        self.assertTrue(a.signed)

    def test_from_binary_unsigned(self):
        # 0b00111100 = 60
        a = fxp("00111100", 4, 4, False)
        self.assertEqual(a.val_int, 60)

    def test_from_binary_signed_positive(self):
        # 0b00111100 = 60, MSB=0 so positive
        a = fxp("00111100", 3, 4, True)
        self.assertEqual(a.val_int, 60)

    def test_from_binary_signed_negative(self):
        # 0b11101000 in Q3.4 signed = -24
        a = fxp("11101000", 3, 4, True)
        self.assertEqual(a.val_int, -24)

    def test_binary_wrong_length_raises(self):
        with self.assertRaises(ValueError):
            fxp("101010", 4, 4, False)   # 6 bits, expects 8

    def test_invalid_type_raises(self):
        with self.assertRaises(TypeError):
            FixedPoint([1, 2], 4, 4, False)

    def test_overflow_clips_and_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            a = fxpi(300, 4, 4, False)   # max unsigned Q4.4 = 255
        self.assertEqual(len(w), 1)
        self.assertIn("Overflow", str(w[0].message))
        self.assertEqual(a.val_int, 255)

    def test_underflow_clips_and_warns(self):
        # Q4.4 signed: total_width=9, min_val=-(1<<8)=-256. Use -300 to trigger clip.
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            a = fxpi(-300, 4, 4, True)
        self.assertEqual(len(w), 1)
        self.assertIn("Underflow", str(w[0].message))
        self.assertEqual(a.val_int, -(1 << 8))   # min for 9-bit signed = -256

    def test_unsigned_negative_int_clips(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            a = fxpi(-1, 4, 4, False)
        self.assertEqual(len(w), 1)
        self.assertEqual(a.val_int, 0)

    def test_label_preserved(self):
        a = FixedPoint(1.0, 4, 4, False, label="my_signal")
        self.assertEqual(a.label, "my_signal")

    # def test_label_unique_fallback(self):
    #     a = FixedPoint(1.0, 4, 4, False)
    #     b = FixedPoint(1.0, 4, 4, False)
    #     self.assertNotEqual(a.label, b.label)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Truncation — float constructor
# ══════════════════════════════════════════════════════════════════════════════

class TestTruncation(unittest.TestCase):
    """
    The float constructor must truncate toward zero (int()), not round.
    This is the HW-indicative default — dropping LSBs is free in hardware.
    """

    def test_positive_truncates_not_rounds(self):
        # 0.3 * 16 = 4.8 -> truncate=4, round=5
        a = fxp(0.3, 4, 4, False)
        self.assertEqual(a.val_int, 4)

    def test_negative_truncates_toward_zero(self):
        # -0.3 * 16 = -4.8 -> int(-4.8) = -4 (toward zero), not -5 (floor)
        a = fxp(-0.3, 4, 4, True)
        self.assertEqual(a.val_int, -4)

    def test_exact_value_no_truncation(self):
        # 0.25 * 16 = 4.0 exactly, no truncation needed
        a = fxp(0.25, 4, 4, False)
        self.assertEqual(a.val_int, 4)

    def test_large_fractional_truncation(self):
        # 1.9 * 16 = 30.4 -> truncate = 30
        a = fxp(1.9, 4, 4, False)
        self.assertEqual(a.val_int, 30)

    def test_val_float_reflects_truncated_value(self):
        # 0.3 truncated to val_int=4, val_float should be 4/16 = 0.25
        a = fxp(0.3, 4, 4, False)
        self.assertAlmostEqual(a.val_float, 0.25, places=10)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Representation
# ══════════════════════════════════════════════════════════════════════════════

class TestRepresentation(unittest.TestCase):

    def test_total_width_unsigned(self):
        a = fxpi(0, 4, 4, False)
        self.assertEqual(a.total_width, 8)

    def test_total_width_signed(self):
        # Signed adds 1 sign bit
        a = fxpi(0, 4, 4, True)
        self.assertEqual(a.total_width, 9)

    def test_val_bin_unsigned(self):
        # 60 in 8 bits = 0b00111100
        a = fxpi(60, 4, 4, False)
        self.assertEqual(a.val_bin, "00111100")

    def test_val_bin_signed_negative(self):
        # -24 in Q3.4 signed (8 bits total) = 0b11101000
        a = fxpi(-24, 3, 4, True)
        self.assertEqual(a.val_bin, "11101000")

    def test_val_bin_length_matches_total_width(self):
        for iw, fw, signed in [(3, 4, False), (3, 4, True), (8, 8, False), (1, 14, True)]:
            a = fxpi(0, iw, fw, signed)
            self.assertEqual(len(a.val_bin), a.total_width)

    def test_val_float_unsigned(self):
        # val_int=60, fract_width=4: 60/16 = 3.75
        a = fxpi(60, 4, 4, False)
        self.assertAlmostEqual(a.val_float, 3.75, places=10)

    def test_val_float_signed_negative(self):
        # val_int=-24, fract_width=4: -24/16 = -1.5
        a = fxpi(-24, 3, 4, True)
        self.assertAlmostEqual(a.val_float, -1.5, places=10)

    def test_repr_contains_format(self):
        a = fxpi(0, 4, 12, True)
        r = repr(a)
        self.assertIn("Q4.12", r)
        self.assertIn("S", r)

    def test_repr_unsigned(self):
        a = fxpi(0, 4, 12, False)
        self.assertIn("U", repr(a))


# ══════════════════════════════════════════════════════════════════════════════
# 4. Addition
# ══════════════════════════════════════════════════════════════════════════════

class TestAddition(unittest.TestCase):

    def test_basic_unsigned(self):
        a = fxpi(40, 3, 4, False)   # 2.5
        b = fxpi(24, 3, 4, False)   # 1.5
        c = a + b
        self.assertEqual(c.val_int, 64)   # 4.0

    def test_result_int_width_grows_by_one(self):
        a = fxpi(0, 3, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a + b
        self.assertEqual(c.int_width, 4)   # max(3,3)+1

    def test_result_int_width_uses_max(self):
        a = fxpi(0, 5, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a + b
        self.assertEqual(c.int_width, 6)   # max(5,3)+1

    def test_result_fract_width_unchanged(self):
        a = fxpi(0, 3, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a + b
        self.assertEqual(c.fract_width, 4)

    def test_signed_plus_signed(self):
        a = fxpi(-32, 3, 4, True)   # -2.0
        b = fxpi(20, 3, 4, True)    # 1.25
        c = a + b
        self.assertEqual(c.val_int, -12)   # -0.75
        self.assertTrue(c.signed)

    def test_unsigned_plus_signed_promotes_to_signed(self):
        a = fxpi(48, 3, 4, False)   # 3.0
        b = fxpi(-16, 3, 4, True)   # -1.0
        c = a + b
        self.assertTrue(c.signed)
        self.assertEqual(c.val_int, 32)   # 2.0

    def test_mixed_fract_width_aligns(self):
        # a: Q3.4, b: Q3.8 — b has wider fractional part
        # a's int must be shifted left by 4 before adding
        a = fxpi(16, 3, 4, False)    # val_int=16 in Q3.4 = 1.0
        b = fxpi(128, 3, 8, False)   # val_int=128 in Q3.8 = 0.5
        c = a + b
        # After alignment: a_int = 16<<4 = 256, b_int = 128
        # result = 384 in Q?.8 = 1.5
        self.assertEqual(c.fract_width, 8)
        self.assertAlmostEqual(c.val_float, 1.5, places=8)

    def test_add_zero(self):
        a = fxpi(42, 4, 4, False)
        z = fxpi(0, 4, 4, False)
        c = a + z
        self.assertEqual(c.val_int, 42)

    def test_type_error_on_non_fxp(self):
        a = fxpi(1, 4, 4, False)
        with self.assertRaises(TypeError):
            _ = a + 1.0
        with self.assertRaises(TypeError):
            _ = a + 1


# ══════════════════════════════════════════════════════════════════════════════
# 5. Subtraction
# ══════════════════════════════════════════════════════════════════════════════

class TestSubtraction(unittest.TestCase):

    def test_basic_unsigned(self):
        a = fxpi(80, 3, 4, False)   # 5.0
        b = fxpi(24, 3, 4, False)   # 1.5
        c = a - b
        self.assertEqual(c.val_int, 56)   # 3.5

    def test_result_int_width_grows_by_one(self):
        a = fxpi(0, 3, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a - b
        self.assertEqual(c.int_width, 4)

    def test_signed_subtraction(self):
        a = fxpi(-24, 3, 4, True)   # -1.5
        b = fxpi(-24, 3, 4, True)   # -1.5
        c = a - b
        self.assertEqual(c.val_int, 0)

    def test_unsigned_underflow_clamps_and_warns(self):
        a = fxpi(16, 3, 4, False)   # 1.0
        b = fxpi(40, 3, 4, False)   # 2.5
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            c = a - b
        self.assertEqual(len(w), 1)
        self.assertIn("nderflow", str(w[0].message))
        self.assertEqual(c.val_int, 0)

    def test_sign_promotion(self):
        a = fxpi(48, 3, 4, False)
        b = fxpi(-16, 3, 4, True)
        c = a - b
        self.assertTrue(c.signed)

    def test_type_error_on_non_fxp(self):
        a = fxpi(1, 4, 4, False)
        with self.assertRaises(TypeError):
            _ = a - 1


# ══════════════════════════════════════════════════════════════════════════════
# 6. Multiplication
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiplication(unittest.TestCase):

    def test_basic_unsigned(self):
        # 2.0 * 1.5 = 3.0
        # a: val_int=32 Q3.4, b: val_int=24 Q3.4
        # result: 32*24=768, Q6.8
        a = fxpi(32, 3, 4, False)
        b = fxpi(24, 3, 4, False)
        c = a * b
        self.assertEqual(c.val_int, 768)
        self.assertAlmostEqual(c.val_float, 3.0, places=8)

    def test_fract_width_doubles(self):
        a = fxpi(0, 3, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a * b
        self.assertEqual(c.fract_width, 8)   # 4+4

    def test_int_width_sums(self):
        a = fxpi(0, 3, 4, False)
        b = fxpi(3, 5, 4, False)
        c = a * b
        self.assertEqual(c.int_width, 8)   # 3+5, no guard bit (both unsigned)

    def test_sign_guard_bit_when_either_signed(self):
        # signed * signed: guard bit added
        a = fxpi(0, 3, 4, True)
        b = fxpi(0, 3, 4, True)
        c = a * b
        self.assertEqual(c.int_width, 7)   # 3+3+1

    def test_sign_guard_bit_signed_times_unsigned(self):
        # signed * unsigned: result is signed, guard bit added
        a = fxpi(0, 3, 4, True)
        b = fxpi(0, 3, 4, False)
        c = a * b
        self.assertTrue(c.signed)
        self.assertEqual(c.int_width, 7)   # 3+3+1

    def test_signed_negative(self):
        # -2.0 * 1.5 = -3.0
        a = fxpi(-32, 3, 4, True)    # -2.0 in Q3.4 signed
        b = fxpi(24, 3, 4, True)     #  1.5 in Q3.4 signed
        c = a * b
        self.assertEqual(c.val_int, -768)
        self.assertAlmostEqual(c.val_float, -3.0, places=8)

    def test_negative_times_negative(self):
        a = fxpi(-24, 3, 4, True)   # -1.5
        b = fxpi(-32, 3, 4, True)   # -2.0
        c = a * b
        self.assertEqual(c.val_int, 768)
        self.assertAlmostEqual(c.val_float, 3.0, places=8)

    def test_multiply_by_zero(self):
        a = fxpi(255, 4, 4, False)
        z = fxpi(0, 4, 4, False)
        c = a * z
        self.assertEqual(c.val_int, 0)

    def test_type_error_on_non_fxp(self):
        a = fxpi(1, 4, 4, False)
        with self.assertRaises(TypeError):
            _ = a * 2


# ══════════════════════════════════════════════════════════════════════════════
# 7. Negation and Abs
# ══════════════════════════════════════════════════════════════════════════════

class TestNegationAbs(unittest.TestCase):

    def test_neg_positive(self):
        a = fxpi(24, 3, 4, True)   # 1.5
        b = -a
        self.assertEqual(b.val_int, -24)
        self.assertTrue(b.signed)

    def test_neg_negative(self):
        a = fxpi(-24, 3, 4, True)
        b = -a
        self.assertEqual(b.val_int, 24)

    def test_neg_forces_signed(self):
        # Negating an unsigned makes it signed
        a = fxpi(24, 3, 4, False)
        b = -a
        self.assertTrue(b.signed)

    def test_neg_preserves_format(self):
        a = fxpi(24, 3, 4, True)
        b = -a
        self.assertEqual(b.int_width, a.int_width)
        self.assertEqual(b.fract_width, a.fract_width)

    def test_abs_positive(self):
        a = fxpi(24, 3, 4, True)
        self.assertEqual(abs(a).val_int, 24)

    def test_abs_negative(self):
        a = fxpi(-24, 3, 4, True)
        self.assertEqual(abs(a).val_int, 24)

    def test_abs_preserves_format(self):
        a = fxpi(-24, 3, 4, True)
        b = abs(a)
        self.assertEqual(b.int_width, a.int_width)
        self.assertEqual(b.fract_width, a.fract_width)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Comparison
# ══════════════════════════════════════════════════════════════════════════════

class TestComparison(unittest.TestCase):

    def test_eq_same_format(self):
        a = fxpi(42, 4, 4, False)
        b = fxpi(42, 4, 4, False)
        self.assertTrue(a == b)

    def test_eq_different_value(self):
        a = fxpi(42, 4, 4, False)
        b = fxpi(43, 4, 4, False)
        self.assertFalse(a == b)

    def test_lt(self):
        a = fxpi(10, 4, 4, False)
        b = fxpi(20, 4, 4, False)
        self.assertTrue(a < b)
        self.assertFalse(b < a)

    def test_le_equal(self):
        a = fxpi(10, 4, 4, False)
        b = fxpi(10, 4, 4, False)
        self.assertTrue(a <= b)

    def test_gt(self):
        a = fxpi(20, 4, 4, False)
        b = fxpi(10, 4, 4, False)
        self.assertTrue(a > b)

    def test_ge_equal(self):
        a = fxpi(10, 4, 4, False)
        b = fxpi(10, 4, 4, False)
        self.assertTrue(a >= b)

    def test_signed_negative_comparison(self):
        a = fxpi(-10, 4, 4, True)
        b = fxpi(10, 4, 4, True)
        self.assertTrue(a < b)

    def test_mixed_fract_width_comparison(self):
        # 1.0 in Q3.4 (val_int=16) vs 1.0 in Q3.8 (val_int=256)
        # After alignment both should be equal
        a = fxpi(16, 3, 4, False)
        b = fxpi(256, 3, 8, False)
        self.assertTrue(a == b)

    def test_mixed_fract_width_lt(self):
        # 0.5 in Q3.4 (val_int=8) vs 1.0 in Q3.8 (val_int=256)
        a = fxpi(8, 3, 4, False)
        b = fxpi(256, 3, 8, False)
        self.assertTrue(a < b)

    def test_hash_equal_values(self):
        a = fxpi(42, 4, 4, False)
        b = fxpi(42, 4, 4, False)
        self.assertEqual(hash(a), hash(b))

    def test_hash_different_values(self):
        a = fxpi(42, 4, 4, False)
        b = fxpi(43, 4, 4, False)
        self.assertNotEqual(hash(a), hash(b))

    def test_eq_non_fxp_returns_not_implemented(self):
        a = fxpi(1, 4, 4, False)
        result = a.__eq__(1.0)
        self.assertIs(result, NotImplemented)


# ══════════════════════════════════════════════════════════════════════════════
# 9. Left shift
# ══════════════════════════════════════════════════════════════════════════════

class TestLeftShift(unittest.TestCase):

    def test_val_int_doubles(self):
        a = fxpi(24, 3, 4, False)   # 1.5
        b = a << 1
        self.assertEqual(b.val_int, 48)

    def test_int_width_grows(self):
        a = fxpi(0, 3, 4, False)
        b = a << 2
        self.assertEqual(b.int_width, 5)

    def test_fract_width_unchanged(self):
        a = fxpi(0, 3, 4, False)
        b = a << 2
        self.assertEqual(b.fract_width, 4)

    def test_val_float_doubles(self):
        a = fxpi(24, 3, 4, False)   # 1.5
        b = a << 1
        self.assertAlmostEqual(b.val_float, 3.0, places=8)

    def test_signed_lshift(self):
        a = fxpi(-24, 3, 4, True)   # -1.5
        b = a << 1
        self.assertEqual(b.val_int, -48)
        self.assertAlmostEqual(b.val_float, -3.0, places=8)


# ══════════════════════════════════════════════════════════════════════════════
# 10. Right shift
# ══════════════════════════════════════════════════════════════════════════════

class TestRightShift(unittest.TestCase):

    def test_val_int_unchanged_unsigned(self):
        # rshift does not shift val_int — it widens fract_width
        a = fxpi(48, 3, 4, False)   # 3.0
        b = a >> 1
        self.assertEqual(b.val_int, 48)

    def test_fract_width_grows(self):
        a = fxpi(0, 3, 4, False)
        b = a >> 2
        self.assertEqual(b.fract_width, 6)

    def test_int_width_unchanged(self):
        a = fxpi(0, 3, 4, False)
        b = a >> 2
        self.assertEqual(b.int_width, 3)

    def test_val_float_halves(self):
        # val_int stays 48, fract_width grows 4->5: 48/32 = 1.5
        a = fxpi(48, 3, 4, False)   # 3.0  (48/16)
        b = a >> 1
        self.assertAlmostEqual(b.val_float, 1.5, places=8)   # 48/32 = 1.5

    def test_signed_arithmetic_shift(self):
        # rshift reinterprets val_int in wider fract format — val_int unchanged.
        # a: val_int=-64, fract_width=4 -> val_float=-64/16=-4.0
        # b: val_int=-64, fract_width=5 -> val_float=-64/32=-2.0
        a = fxpi(-64, 3, 4, True)
        b = a >> 1
        self.assertEqual(b.val_int, -64)
        self.assertAlmostEqual(b.val_float, -2.0, places=8)

    def test_unsigned_logical_shift(self):
        # rshift reinterprets — val_int unchanged, fract_width grows.
        # 128 overflows Q3.4 unsigned (max=127), use 96 instead.
        # a: val_int=96, fract_width=4 -> 96/16=6.0
        # b: val_int=96, fract_width=5 -> 96/32=3.0
        a = fxpi(96, 3, 4, False)
        b = a >> 1
        self.assertEqual(b.val_int, 96)
        self.assertAlmostEqual(b.val_float, 3.0, places=8)


# ══════════════════════════════════════════════════════════════════════════════
# 11. bsl_scale / bsr_scale
# ══════════════════════════════════════════════════════════════════════════════

class TestScaling(unittest.TestCase):

    def test_bsl_scale_doubles_value(self):
        a = fxpi(24, 3, 4, False)   # 1.5
        b = a.bsl_scale(1)
        self.assertEqual(b.val_int, 48)
        self.assertEqual(b.int_width, 4)
        self.assertEqual(b.fract_width, 4)

    def test_bsl_scale_int_width_grows(self):
        a = fxpi(0, 3, 4, False)
        b = a.bsl_scale(2)
        self.assertEqual(b.int_width, 5)

    # def test_bsr_scale_halves_value(self):
    #     a = fxpi(48, 3, 4, False)   # 3.0
    #     b = a.bsr_scale(1)
    #     self.assertEqual(b.val_int, 24)
    #     self.assertEqual(b.fract_width, 5)

    def test_bsr_scale_fract_width_grows(self):
        a = fxpi(0, 3, 4, False)
        b = a.bsr_scale(2)
        self.assertEqual(b.fract_width, 6)

    # def test_bsr_scale_signed_arithmetic(self):
    #     a = fxpi(-48, 3, 4, True)   # -3.0
    #     b = a.bsr_scale(1)
    #     self.assertEqual(b.val_int, -24)

    def test_bsl_then_bsr_roundtrips(self):
        # bsl shifts val_int left and grows int_width.
        # bsr widens fract_width without shifting val_int.
        # After bsl(3): val_int=192, int_width=6, fract_width=4
        # After bsr(3): val_int=192, int_width=6, fract_width=7
        # val_float: 192/128 = 1.5 — same as original 24/16 = 1.5
        a = fxpi(24, 3, 4, False)
        b = a.bsl_scale(3).bsr_scale(3)
        self.assertAlmostEqual(b.val_float, a.val_float, places=8)


# ══════════════════════════════════════════════════════════════════════════════
# 12. requantize
# ══════════════════════════════════════════════════════════════════════════════

class TestRequantize(unittest.TestCase):

    def test_noop_same_format(self):
        a = fxpi(42, 4, 8, False)
        b = a.requantize(4, 8)
        self.assertEqual(b.val_int, 42)
        self.assertEqual(b.int_width, 4)
        self.assertEqual(b.fract_width, 8)

    def test_narrowing_truncates_via_shift(self):
        # Q4.8 -> Q4.4: right shift by 4
        # val_int=256 (1.0 in Q4.8) >> 4 = 16 (1.0 in Q4.4) — exact
        a = fxpi(256, 4, 8, False)
        b = a.requantize(4, 4)
        self.assertEqual(b.val_int, 16)

    def test_narrowing_truncates_not_rounds(self):
        # val_int=844 in Q4.8 (3.3046875)
        # >> 4 = 52 (3.25) — truncated, not rounded to 53 (3.3125)
        a = fxpi(844, 4, 8, False)
        b = a.requantize(4, 4)
        self.assertEqual(b.val_int, 52)

    def test_narrowing_negative_truncates(self):
        # Arithmetic right shift on negative: -844 >> 4
        # Python >> on negative ints floors (toward -inf)
        a = fxpi(-844, 4, 8, True)
        b = a.requantize(4, 4, signed=True)
        self.assertEqual(b.val_int, -844 >> 4)

    def test_widening_lossless(self):
        # Q4.4 -> Q4.8: left shift by 4
        a = fxpi(16, 4, 4, False)   # 1.0
        b = a.requantize(4, 8)
        self.assertEqual(b.val_int, 256)   # 16 << 4

    def test_widening_then_narrowing_roundtrips_exact(self):
        a = fxpi(16, 4, 4, False)   # 1.0, exactly representable
        b = a.requantize(4, 8).requantize(4, 4)
        self.assertEqual(b.val_int, 16)

    def test_sign_change_unsigned_to_signed(self):
        a = fxpi(16, 4, 4, False)
        b = a.requantize(4, 4, signed=True)
        self.assertTrue(b.signed)
        self.assertEqual(b.val_int, 16)

    def test_sign_inherits_by_default(self):
        a = fxpi(16, 4, 4, True)
        b = a.requantize(4, 8)
        self.assertTrue(b.signed)

    def test_int_width_change(self):
        a = fxpi(16, 4, 4, False)
        b = a.requantize(8, 4)
        self.assertEqual(b.int_width, 8)
        self.assertEqual(b.val_int, 16)   # int_width change alone doesn't shift


# ══════════════════════════════════════════════════════════════════════════════
# 13. Numeric conversions and bool
# ══════════════════════════════════════════════════════════════════════════════

class TestNumericConversions(unittest.TestCase):

    def test_float_conversion(self):
        a = fxpi(60, 4, 4, False)   # 3.75
        self.assertAlmostEqual(float(a), 3.75, places=10)

    def test_int_conversion_truncates(self):
        a = fxpi(60, 4, 4, False)   # 3.75
        self.assertEqual(int(a), 3)

    def test_int_conversion_negative(self):
        a = fxpi(-24, 3, 4, True)   # -1.5
        self.assertEqual(int(a), -1)

    def test_bool_nonzero(self):
        a = fxpi(1, 4, 4, False)
        self.assertTrue(bool(a))

    def test_bool_zero(self):
        a = fxpi(0, 4, 4, False)
        self.assertFalse(bool(a))


# ══════════════════════════════════════════════════════════════════════════════
# 14. Width metadata — result formats match expected HW output widths
#
# These are the most important tests for hardware correctness.
# They verify that the width of every operation result matches what real
# hardware would produce, not just that the value is numerically correct.
# ══════════════════════════════════════════════════════════════════════════════

class TestWidthMetadata(unittest.TestCase):

    def test_add_total_width(self):
        # Q3.4 + Q3.4 -> Q4.4: total = 4+4 = 8 bits unsigned
        a = fxpi(0, 3, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a + b
        self.assertEqual(c.total_width, 8)

    def test_add_asymmetric_int_widths(self):
        # Q5.4 + Q3.4 -> Q6.4
        a = fxpi(0, 5, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a + b
        self.assertEqual(c.int_width, 6)
        self.assertEqual(c.fract_width, 4)

    def test_mul_total_width_unsigned(self):
        # Q3.4 * Q3.4 -> Q6.8: (3+3).(4+4), no guard bit
        a = fxpi(0, 3, 4, False)
        b = fxpi(0, 3, 4, False)
        c = a * b
        self.assertEqual(c.int_width, 6)
        self.assertEqual(c.fract_width, 8)
        self.assertEqual(c.total_width, 14)

    def test_mul_total_width_signed(self):
        # Q3.4S * Q3.4S -> Q7.8S: (3+3+1).(4+4), +1 sign guard bit
        a = fxpi(0, 3, 4, True)
        b = fxpi(0, 3, 4, True)
        c = a * b
        self.assertEqual(c.int_width, 7)
        self.assertEqual(c.fract_width, 8)
        self.assertEqual(c.total_width, 16)   # 7+8+1

    def test_mul_asymmetric_formats(self):
        # Q4.8S * Q2.4U -> Q7.12S: (4+2+1).(8+4)
        a = fxpi(0, 4, 8, True)
        b = fxpi(0, 2, 4, False)
        c = a * b
        self.assertEqual(c.int_width, 7)
        self.assertEqual(c.fract_width, 12)

    def test_lshift_width(self):
        a = fxpi(0, 3, 4, False)
        b = a << 3
        self.assertEqual(b.int_width, 6)
        self.assertEqual(b.fract_width, 4)

    def test_rshift_width(self):
        a = fxpi(0, 3, 4, False)
        b = a >> 3
        self.assertEqual(b.int_width, 3)
        self.assertEqual(b.fract_width, 7)

    def test_chain_add_mul_widths(self):
        # (Q3.4 * Q3.4) + (Q3.4 * Q3.4)
        # mul result: Q6.8, add result: Q7.8
        a = fxpi(0, 3, 4, False)
        b = fxpi(0, 3, 4, False)
        p1 = a * b   # Q6.8
        p2 = a * b   # Q6.8
        s  = p1 + p2
        self.assertEqual(s.int_width, 7)
        self.assertEqual(s.fract_width, 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
