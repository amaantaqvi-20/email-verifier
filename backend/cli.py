"""
CLI entry point for Email Verifier
----------------------------------

Usage Examples:
---------------
email-verifier.exe --input sample_files --output output
email-verifier.exe --input emails.csv --output verified --premium
"""

import argparse
import sys
import os
import email_verifier


def main():
    parser = argparse.ArgumentParser(
        description="Bulk Email Verifier - Free Edition (No Paid APIs)"
    )
    parser.add_argument("--input", "-i", required=True, help="Input folder or file path")
    parser.add_argument("--output", "-o", required=True, help="Output folder")
    parser.add_argument("--workers", "-w", type=int, default=50, help="Concurrent threads (default 50)")
    parser.add_argument("--premium", action="store_true", help="Enable deeper SMTP checks (slower, more accurate)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] Input path not found: {args.input}")
        sys.exit(1)

    print("===========================================")
    print("       Email Verifier - Free Edition        ")
    print("===========================================")
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Mode: {'Premium' if args.premium else 'Fast Free'}")
    print("===========================================")

    email_verifier.main(args)
    print("\n✅ Verification completed successfully!")


if __name__ == "__main__":
    main()
