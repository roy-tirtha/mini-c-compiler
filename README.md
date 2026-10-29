# Tiny C Compiler

A small compiler for a C-like language, written in Python 3 (no external packages).
Pipeline: **Lexer → Parser → Semantic Analyzer → Three-Address Code → Interpreter**.

## Requirements

- Python 3.8 or newer

## Running

Run every command from the project root (the folder that contains `tinyc/`).

**1. Compile and run a file**

```
python -m tinyc.main examples/basic.tc
```

**2. Type code directly in the terminal (interactive mode)**

```
python -m tinyc.main
```

Type your program line by line, then enter `run`.
Commands: `run` (compile and execute), `clear` (discard what you typed), `exit`.
`Ctrl+D` (Linux/Mac) or `Ctrl+Z` then Enter (Windows) also runs the typed code.

**3. Pass code on the command line**

```
python -m tinyc.main -c "int a = 4; print(a * 2);"
```

**4. Pipe code in**

```
echo 'print(1 + 2);' | python -m tinyc.main
```

## Useful flags

| Flag | What it does |
|------|--------------|
| `--tokens` | print the token list from the lexer |
| `--ast` | print the syntax tree |
| `--tac` | print the generated three-address code |
| `--no-run` | check/compile only, do not execute |
| `--max-steps N` | stop execution after N instructions (infinite-loop guard) |
| `--no-color` | disable coloured error output |

Example: `python -m tinyc.main examples/loop.tc --tokens --ast --tac`

## Example programs

| File | Shows |
|------|-------|
| `examples/basic.tc` | variables, assignment, print |
| `examples/arithmetic.tc` | operators, precedence, int/float |
| `examples/conditional.tc` | if / else if / else, `&&`, `\|\|` |
| `examples/loop.tc` | while, for, break, continue |
| `examples/input.tc` | reading a number with `read()` (type a number when prompted) |
| `examples/invalid.tc` | syntax errors (several reported at once) |
| `examples/invalid_semantic.tc` | semantic errors and warnings |

## Tiny C at a glance

```c
int n = 5;                 // types: int, float
float avg;
read(n);                   // read a number from the user
n += 2;  n++;              // = += -= *= /=  ++  --
if (n > 3 && n != 9) { print("n is", n); } else { print("small"); }
while (n > 0) { n--; }
for (int i = 0; i < 3; i++) { if (i == 1) { continue; } print(i); }
```

Operators: `+ - * / %`, `< <= > >= == !=`, `&& || !`.
Comments: `// line` and `/* block */`. Strings are allowed only inside `print(...)`.

## Running the tests

```
python -m unittest discover -s tests -v
```

(If you use pytest: `python -m pytest tests`.)

## Exit codes

`0` success · `1` compile error · `2` runtime error · `3` file error
