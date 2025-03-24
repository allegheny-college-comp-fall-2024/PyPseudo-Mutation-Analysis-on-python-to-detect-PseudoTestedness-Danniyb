import json

# Load the unmutated test results
with open('report_unmutated.json', 'r') as f:
    unmutated_report = json.load(f)

# Load the mutated test results
with open('report_mutated.json', 'r') as f:
    mutated_report = json.load(f)

# Load the unmutated coverage
with open('coverage_unmutated.json', 'r') as f:
    unmutated_coverage = json.load(f)

# Load the mutated coverage
with open('coverage_mutated.json', 'r') as f:
    mutated_coverage = json.load(f)

# Example of combining the results into a final report
final_report = {
    "test_comparison": {
        "unmutated": unmutated_report,
        "mutated": mutated_report
    },
    "coverage_comparison": {
        "unmutated": unmutated_coverage,
        "mutated": mutated_coverage
    }
}

# Write the final combined report to a JSON file
with open('final_report.json', 'w') as f:
    json.dump(final_report, f, indent=4)

print("Final comparison report generated: final_report.json")
