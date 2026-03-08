"""
Test the CV Parser with Profile.pdf
"""
import sys
import json
sys.path.insert(0, 'api')

print("="*60)
print("CV PARSER TEST")
print("="*60)

# Test 1: Import the parser
print("\n[1/3] Loading CV Parser...")
try:
    from LinkedIn_PDF_Reader_Talendeur_for_microservices import CVParser
    print("✓ CVParser imported successfully")
    if CVParser().nlp is None:
        print("⚠ SpaCy model not loaded (NLP features disabled)")
    else:
        print("✓ SpaCy NLP model loaded")
except Exception as e:
    print(f"✗ Failed to import: {e}")
    sys.exit(1)

# Test 2: Load the PDF
print("\n[2/3] Reading Profile.pdf...")
try:
    with open("Profile.pdf", "rb") as f:
        pdf_bytes = f.read()
    print(f"✓ PDF loaded ({len(pdf_bytes):,} bytes)")
except FileNotFoundError:
    print("✗ Profile.pdf not found")
    sys.exit(1)

# Test 3: Parse the CV
print("\n[3/3] Parsing CV data...")
try:
    parser = CVParser()
    result = parser.parse(pdf_bytes)
    print("✓ Parsing completed successfully!")
    
    # Display results
    print("\n" + "="*60)
    print("EXTRACTED DATA")
    print("="*60)
    
    # Profile info
    profile = result.get('profile', {})
    print(f"\n📋 PROFILE:")
    print(f"   Name: {profile.get('name', 'N/A')}")
    print(f"   Title: {profile.get('headline', 'N/A')}")
    print(f"   Email: {profile.get('email', 'N/A')}")
    print(f"   Phone: {profile.get('phone', 'N/A')}")
    print(f"   Location: {profile.get('city', 'N/A')}, {profile.get('country', 'N/A')}")
    
    # Experience
    experience = result.get('experience', [])
    print(f"\n💼 EXPERIENCE: {len(experience)} positions")
    for i, exp in enumerate(experience[:3], 1):  # Show first 3
        print(f"   {i}. {exp.get('role', 'N/A')} at {exp.get('company', 'N/A')}")
        print(f"      {exp.get('start_date', '')} - {exp.get('end_date', '')}")
    
    # Education
    education = result.get('education', [])
    print(f"\n🎓 EDUCATION: {len(education)} entries")
    for i, edu in enumerate(education[:2], 1):  # Show first 2
        print(f"   {i}. {edu.get('degree', 'N/A')}")
        print(f"      {edu.get('institution', 'N/A')}")
    
    # Skills
    skills = result.get('skills', [])
    print(f"\n🛠️  SKILLS: {len(skills)} skills found")
    if skills:
        skill_names = [s.get('skill_name', s) if isinstance(s, dict) else s for s in skills[:10]]
        print(f"   {', '.join(skill_names)}")
    
    # Languages
    languages = result.get('languages', [])
    print(f"\n🌍 LANGUAGES: {len(languages)} languages")
    for lang in languages[:5]:
        name = lang.get('language', 'N/A')
        level = lang.get('proficiency_level', 'N/A')
        print(f"   • {name}: {level}")
    
    # Certifications
    certs = result.get('certifications', [])
    print(f"\n📜 CERTIFICATIONS: {len(certs)} certifications")
    for cert in certs[:5]:
        print(f"   • {cert}")
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED!")
    print("="*60)
    
    # Save full output
    with open("test_output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("\n💾 Full output saved to: test_output.json")
    
except Exception as e:
    print(f"✗ Parsing failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ The API is ready to deploy!")
print("   Next: Deploy to Netlify and test from your React app")
