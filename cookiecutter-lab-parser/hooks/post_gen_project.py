import os
import shutil

LAB_SLUG = "{{cookiecutter.lab_slug}}"

# Hook runs from inside the generated folder: <project_root>/<lab_slug>/
# So project root is one level up.
project_root = os.path.abspath("..")
generated_dir = os.getcwd()

# Destination paths
parser_dest = os.path.join(project_root, "parsers", LAB_SLUG)
tests_dest  = os.path.join(project_root, "tests")
fixture_dest = os.path.join(project_root, "tests", "fixtures", LAB_SLUG)

# Create parsers/{lab_slug}/
os.makedirs(parser_dest, exist_ok=True)

# Move parser files
for fname in ["__init__.py", "parser.py", "_helpers.py"]:
    shutil.move(os.path.join(generated_dir, fname), os.path.join(parser_dest, fname))

# Move test file
test_fname = f"test_{LAB_SLUG}_parser.py"
shutil.move(os.path.join(generated_dir, test_fname), os.path.join(tests_dest, test_fname))

# Create fixture directory
os.makedirs(fixture_dest, exist_ok=True)

# Remove the (now empty) generated folder
os.chdir(project_root)
shutil.rmtree(generated_dir)

print(f"\n  Parser '{LAB_SLUG}' scaffolded successfully!\n")
print(f"  Files created:")
print(f"    parsers/{LAB_SLUG}/__init__.py")
print(f"    parsers/{LAB_SLUG}/parser.py")
print(f"    parsers/{LAB_SLUG}/_helpers.py")
print(f"    tests/test_{LAB_SLUG}_parser.py")
print(f"    tests/fixtures/{LAB_SLUG}/  (add sample.pdf here)\n")
print(f"  Next steps:")
print(f"    1. Implement parse logic in parsers/{LAB_SLUG}/_helpers.py")
print(f"    2. Add {{cookiecutter.lab_class_name}}() to parsers/registry.py")
print(f"    3. Copy a sample PDF to tests/fixtures/{LAB_SLUG}/sample.pdf")
print(f"    4. Run: pytest tests/test_{LAB_SLUG}_parser.py -v\n")
