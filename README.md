# PyFxP

**PyFxP** is a Python library for working with fixed-point numbers using the Qm.n format. It allows users to create fixed-point values, perform arithmetic operations with correct bit-width promotion, track overflows, and inspect binary representations — all in a form that mirrors how hardware interprets fixed-point arithmetic.

---

## Features

- Supports signed and unsigned Qm.n format (two's complement for signed)
- Automatically handles overflow and underflow warnings
- Promotes bit-widths in arithmetic operations to prevent overflow
- Tracks internal representation: float, int, and binary
- Ideal for prototyping fixed-point DSP or hardware models in Python

---

## Installation

```bash
git clone https://github.com/yourusername/PyFxP.git
cd PyFxP
pip install .
```

---

## Usage

```python
from PyFxP import FixedPoint

a = FixedPoint(3.5, int_width=3, fract_width=4, signed=True)
b = FixedPoint(-2.0, int_width=3, fract_width=4, signed=True)

c = a + b
print(c.val_float)  # 1.5
print(c.val_bin)    # Binary representation with sign
```

Arithmetic operations automatically promote bit-widths:
- `a + b` → Q(m+1).n
- `a * b` → Q(m1 + m2 [+1 if signed]).(n1 + n2)

---

## Tests

Run all tests with:

```bash
python -m unittest discover -s test
```

---

## Project Structure

```
PyFxP/
├── PyFxP/                 # Library code
│   ├── fix_point.py       # Main FixedPoint class
│   ├── registry.py        # Optional registry for tracking instances and operations
│   └── __init__.py
├── test/                  # Unit tests
├── setup.py
├── pyproject.toml
```

---

## License

MIT License.
