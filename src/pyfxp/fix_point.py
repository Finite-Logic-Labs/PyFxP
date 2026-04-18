import warnings

from .node import Node, NodeType, NodeEnum
from .graph import Graph
from .types import SignType


class FixedPoint:
    """
    FixedPoint represents a value using a Qm.n fixed-point format.

    All arithmetic operates on the underlying integer representation directly.
    Float values are only used at the input boundary (construction from float)
    and output boundary (val_float property). This mirrors how real hardware
    works — the bit pattern is the value.

    Truncation is the default rounding mode throughout: the float constructor
    truncates toward zero, and requantize uses arithmetic right shift. Both
    are free in hardware.
    """

    def __init__(
        self,
        val: int | float | str,
        int_width: int,
        fract_width: int,
        signed: bool | SignType = False,
        label: str = None,
    ):
        self._int_width: int = int_width
        self._fract_width: int = fract_width
        self._signed: SignType = signed if isinstance(signed, SignType) else SignType(signed)

        self._total_width: int = int_width + fract_width + (1 if self._signed.val else 0)

        # Bounds
        self._min_val = -(1 << (self._total_width - 1)) if self._signed.val else 0
        self._max_val = (
            (1 << (self._total_width - 1)) - 1
            if self._signed.val
            else (1 << self._total_width) - 1
        )

        # Convert input
        match val:
            case int():
                raw_int_val = val
            case float():
                raw_int_val = int(val * (1 << self._fract_width))  # truncate toward zero — free in HW
            case str():
                raw_int_val = self._bin_to_int(val)
            case _:
                raise TypeError("Value must be float, int, or binary str")

        # Clip
        if raw_int_val > self._max_val:
            warnings.warn(
                f"Overflow: Value {raw_int_val} exceeds maximum {self._max_val} and will be clipped",
                RuntimeWarning,
            )
            self._val_int = self._max_val
        elif raw_int_val < self._min_val:
            warnings.warn(
                f"Underflow: Value {raw_int_val} below minimum {self._min_val} and will be clipped",
                RuntimeWarning,
            )
            self._val_int = self._min_val
        else:
            self._val_int = raw_int_val

        self._val_float = self._int_to_float(self._val_int)
        self._val_bin = self._int_to_bin(self._val_int)

        # User-provided label is preserved; unique label is only used as fallback
        self._label = label if label is not None else Graph._unique_label(self)

        Graph.log(Node(fxp_a=self, fxp_b=None, fxp_res=None, type=NodeType(NodeEnum.VAR)))

    # ==========================================================================
    # Properties
    # ==========================================================================

    @property
    def val_float(self) -> float:
        return self._val_float

    @property
    def val_int(self) -> int:
        return self._val_int

    @property
    def val_bin(self) -> str:
        return self._val_bin

    @property
    def int_width(self) -> int:
        return self._int_width

    @property
    def fract_width(self) -> int:
        return self._fract_width

    @property
    def total_width(self) -> int:
        return self._total_width

    @property
    def signed(self) -> bool:
        return self._signed.val

    @property
    def sign_type(self) -> SignType:
        return self._signed

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, val: str) -> None:
        self._label = val

    # ==========================================================================
    # Internal helpers
    # ==========================================================================

    def _int_to_float(self, val_int: int) -> float:
        if self._signed.val:
            if val_int > self._max_val:
                val_int -= 1 << self._total_width
        return val_int / (1 << self._fract_width)

    def _int_to_bin(self, val_int: int) -> str:
        mask = (1 << self._total_width) - 1
        return format(val_int & mask, f"0{self._total_width}b")

    def _bin_to_int(self, val_bin: str) -> int:
        if len(val_bin) != self._total_width:
            raise ValueError(f"Binary string must be {self._total_width} bits")
        raw = int(val_bin, 2)
        if self._signed.val and val_bin[0] == "1":
            raw -= 1 << self._total_width
        return raw

    def _fract_width_ext(self, fxpb: "FixedPoint"):
        """
        Align two FixedPoint values to the same fractional width by shifting
        the integer representation of the narrower operand left.
        """
        fxpa = self

        if self._fract_width > fxpb.fract_width:
            shift = self._fract_width - fxpb.fract_width
            fxpb = FixedPoint(fxpb.val_int << shift, fxpb.int_width, self._fract_width, fxpb._signed)
        elif self._fract_width < fxpb.fract_width:
            shift = fxpb.fract_width - self._fract_width
            fxpa = FixedPoint(self._val_int << shift, self._int_width, fxpb.fract_width, self._signed)

        return fxpa, fxpb

    # ==========================================================================
    # Arithmetic
    # ==========================================================================

    def __add__(self, fxpb: "FixedPoint") -> "FixedPoint":
        if not isinstance(fxpb, FixedPoint):
            raise TypeError

        fxpa, fxpb = self._fract_width_ext(fxpb)

        result_signed = SignType(fxpa._signed.val or fxpb._signed.val)
        result_fract = fxpa.fract_width
        result_int = max(fxpa.int_width, fxpb.int_width) + 1
        result_val = fxpa.val_int + fxpb.val_int
        result = FixedPoint(result_val, result_int, result_fract, result_signed)

        Graph.log(Node(fxp_a=fxpa, fxp_b=fxpb, fxp_res=result, type=NodeType(NodeEnum.ADD)))
        return result


    def __sub__(self, fxpb: "FixedPoint") -> "FixedPoint":
        if not isinstance(fxpb, FixedPoint):
            raise TypeError

        fxpa, fxpb = self._fract_width_ext(fxpb)

        result_signed = SignType(fxpa._signed.val or fxpb._signed.val)
        result_fract = fxpa.fract_width
        result_int = max(fxpa.int_width, fxpb.int_width) + 1
        result_val = fxpa.val_int - fxpb.val_int

        if not result_signed.val and result_val < 0:
            warnings.warn(
                f"Underflow in unsigned subtraction: result {result_val} clamped to 0",
                RuntimeWarning,
            )
            result_val = 0

        result = FixedPoint(result_val, result_int, result_fract, result_signed)
        Graph.log(Node(fxp_a=fxpa, fxp_b=fxpb, fxp_res=result, type=NodeType(NodeEnum.SUB)))
        return result


    def __mul__(self, fxpb: "FixedPoint") -> "FixedPoint":
        if not isinstance(fxpb, FixedPoint):
            raise TypeError

        result_signed = SignType(self._signed.val or fxpb._signed.val)
        result_int = self._int_width + fxpb.int_width + (1 if result_signed.val else 0)
        result_fract = self._fract_width + fxpb.fract_width
        result_val = self._val_int * fxpb.val_int
        result = FixedPoint(result_val, result_int, result_fract, result_signed)

        Graph.log(Node(fxp_a=self, fxp_b=fxpb, fxp_res=result, type=NodeType(NodeEnum.MUL)))
        return result


    def __neg__(self) -> "FixedPoint":
        return FixedPoint(-self._val_int, self._int_width, self._fract_width, SignType(True))

    def __abs__(self) -> "FixedPoint":
        return FixedPoint(abs(self._val_int), self._int_width, self._fract_width, self._signed)

    # ==========================================================================
    # Comparison
    # ==========================================================================

    def _cmp_val(self, other: "FixedPoint") -> tuple[int, int]:
        """Return aligned integer values for comparison."""
        a, b = self._fract_width_ext(other)
        return a.val_int, b.val_int

    def __eq__(self, other) -> bool:
        if not isinstance(other, FixedPoint):
            return NotImplemented
        a, b = self._cmp_val(other)
        return a == b

    def __lt__(self, other) -> bool:
        if not isinstance(other, FixedPoint):
            return NotImplemented
        a, b = self._cmp_val(other)
        return a < b

    def __le__(self, other) -> bool:
        if not isinstance(other, FixedPoint):
            return NotImplemented
        a, b = self._cmp_val(other)
        return a <= b

    def __gt__(self, other) -> bool:
        if not isinstance(other, FixedPoint):
            return NotImplemented
        a, b = self._cmp_val(other)
        return a > b

    def __ge__(self, other) -> bool:
        if not isinstance(other, FixedPoint):
            return NotImplemented
        a, b = self._cmp_val(other)
        return a >= b

    def __hash__(self):
        return hash((self._val_int, self._int_width, self._fract_width, self._signed.val))

    # ==========================================================================
    # Numeric conversions
    # ==========================================================================

    def __float__(self) -> float:
        return self._val_float

    def __int__(self) -> int:
        return int(self._val_float)

    def __bool__(self) -> bool:
        return self._val_int != 0

    # ==========================================================================
    # Bit shifts
    # ==========================================================================

    def __lshift__(self, n: int) -> "FixedPoint":
        """
        Left-shift the fixed-point value by n bits.
        Increases int_width by n to reflect the expanded integer range;
        fract_width is unchanged. Clipping is applied against the new bounds.
        """
        shifted_val = self._val_int << n
        return FixedPoint(shifted_val, self._int_width + n, self._fract_width, self._signed)

    def __rshift__(self, n: int) -> "FixedPoint":
        """
        Right-shift the fixed-point value by n bits.
        Increases fract_width by n to reflect the expanded fractional range;
        int_width is unchanged. Arithmetic shift for signed, logical for unsigned.
        """
        if self._signed.val:
            shifted_val = self._val_int >> n
        else:
            shifted_val = (self._val_int & ((1 << self._total_width) - 1)) >> n
        return FixedPoint(shifted_val, self._int_width, self._fract_width + n, self._signed)

    # ==========================================================================
    # Scaling
    # ==========================================================================

    def bsl_scale(self, n: int) -> "FixedPoint":
        """Scale up by 2^n, operating on val_int to avoid float rounding."""
        return FixedPoint(self._val_int << n, self._int_width + n, self._fract_width, self._signed)

    def bsr_scale(self, n: int) -> "FixedPoint":
        """Scale down by 2^n, operating on val_int to avoid float rounding."""
        if self._signed.val:
            shifted_val = self._val_int >> n
        else:
            shifted_val = (self._val_int & ((1 << self._total_width) - 1)) >> n
        return FixedPoint(shifted_val, self._int_width, self._fract_width + n, self._signed)

    # ==========================================================================
    # Quantisation helper
    # ==========================================================================

    def requantize(self, int_width: int, fract_width: int, signed: bool | SignType | None = None) -> "FixedPoint":
        """
        Re-express this value in a different Q format via pure integer shift.

        Narrowing (fract_width decreases) is an arithmetic right shift — truncation
        toward negative infinity, free in hardware (just drop the wires).

        Widening (fract_width increases) is a left shift — no information lost.

        Sign defaults to the current sign if not specified.
        """
        target_signed = self._signed if signed is None else (
            signed if isinstance(signed, SignType) else SignType(signed)
        )
        shift = self._fract_width - fract_width
        if shift > 0:
            # Narrowing: arithmetic right shift = truncate, costs nothing in HW
            new_int = self._val_int >> shift
        elif shift < 0:
            # Widening: left shift, no precision lost
            new_int = self._val_int << (-shift)
        else:
            new_int = self._val_int

        return FixedPoint(new_int, int_width, fract_width, target_signed)

    # ==========================================================================
    # Representation
    # ==========================================================================

    def __repr__(self) -> str:
        sign_char = "S" if self.signed else "U"
        return (
            f"FixedPoint({self._val_float}, "
            f"Q{self._int_width}.{self._fract_width}, "
            f"{sign_char}, "
            f"label='{self._label}')"
        )
