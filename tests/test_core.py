"""외부 서비스 없이 실행하는 단위·정적 점검. 실제 RLS 실행 검증을 대체하지 않습니다."""
import copy
import io
from pathlib import Path
import unittest
from PIL import Image
from utils import (parse_roster, class_from_id, csv_bytes, validate_password, validate_url,
                   validate_file, point_totals, make_layout, validate_layout, DEMO_ROSTER)
ROOT=Path(__file__).resolve().parents[1]

class RosterTests(unittest.TestCase):
    def test_vertical(self):
        out=parse_roster(b'student_id,name,class_id\n10101,A,1-1\n10720,B,1-7\n')
        self.assertEqual([r['class_id'] for r in out],['1-1','1-7'])
    def test_wide_ignores_blanks_and_ref(self):
        out=parse_roster('명렬표,,,,\n10101,가,,10201,나\n인원,#REF!,,,\n'.encode())
        self.assertEqual(len(out),2)
    def test_cp949(self):
        out=parse_roster('학번,이름,학급\n10101,시험,1-1'.encode('cp949'))
        self.assertEqual(out[0]['name'],'시험')
    def test_duplicate(self):
        with self.assertRaises(ValueError):parse_roster(b'student_id,name,class_id\n10101,A,1-1\n10101,B,1-1')
    def test_wrong_class(self):
        with self.assertRaises(ValueError):parse_roster(b'student_id,name,class_id\n10101,A,1-2')
    def test_empty(self):
        with self.assertRaises(ValueError):parse_roster(b'')
    def test_class(self):self.assertEqual(class_from_id('10609'),'1-6')
    def test_bad_id(self):
        for s in ['99999','10801','1011',"10101' OR 1=1"]:
            with self.assertRaises(ValueError):class_from_id(s)
    def test_csv_formula_injection(self):
        raw=csv_bytes([{'name':'=1+1','info':'+cmd'}]).decode('utf-8-sig')
        self.assertIn("'=1+1",raw);self.assertIn("'+cmd",raw)
    def test_demo_contains_no_real_names(self):
        self.assertTrue(all(r['name'].startswith('테스트학생') for r in DEMO_ROSTER))

class PureLogicTests(unittest.TestCase):
    def setUp(self):self.students=[{'id':f'u{i}','student_id':f'101{i:02d}','full_name':f'시험{i}'} for i in range(1,21)]
    def test_point_totals(self):
        self.assertEqual(point_totals([{'delta':3,'cancelled':False},{'delta':-2,'cancelled':False},{'delta':8,'cancelled':True}]),(3,2,1))
    def test_points_empty(self):self.assertEqual(point_totals([]),(0,0,0))
    def test_seats(self):
        entries=make_layout(self.students,5,5)
        validate_layout(entries,5,5,{s['id'] for s in self.students})
        self.assertEqual(len(entries),20)
    def test_seats_duplicate_rejected(self):
        entries=make_layout(self.students,5,5);entries[1]['행']=1;entries[1]['열']=1
        with self.assertRaises(ValueError):validate_layout(entries,5,5,{s['id'] for s in self.students})
    def test_seats_other_class_rejected(self):
        entries=make_layout(self.students,5,5);entries[0]['user_id']='other'
        with self.assertRaises(ValueError):validate_layout(entries,5,5,{s['id'] for s in self.students})
    def test_seats_missing_rejected(self):
        with self.assertRaises(ValueError):validate_layout(make_layout(self.students,5,5)[:-1],5,5,{s['id'] for s in self.students})
    def test_seats_too_few(self):
        with self.assertRaises(ValueError):make_layout(self.students,2,5)
    def test_random_groups_balanced(self):
        out=make_layout(self.students,5,5,True,5)
        from collections import Counter
        self.assertEqual(set(Counter(r['조'] for r in out).values()),{4})
    def test_passwords(self):
        validate_password('A-fine-password!')
        for bad in ['short','가'*25]:
            with self.assertRaises(ValueError):validate_password(bad)
    def test_safe_url(self):
        self.assertEqual(validate_url(' https://www.desmos.com/calculator '),'https://www.desmos.com/calculator')
        for bad in ['javascript:alert(1)','http://x.com','https://user:password@example.com','data:text/html,x']:
            with self.assertRaises(ValueError):validate_url(bad)
    def test_image_signature_and_metadata(self):
        data=io.BytesIO();Image.new('RGB',(8,8)).save(data,'PNG')
        clean,mime,ext=validate_file('photo.png',data.getvalue())
        self.assertTrue(clean.startswith(b'\x89PNG'));self.assertEqual(mime,'image/png')
    def test_file_extension(self):
        with self.assertRaises(ValueError):validate_file('run.exe',b'hello')
    def test_pdf_signature(self):
        with self.assertRaises(ValueError):validate_file('fake.pdf',b'notpdf')
    def test_file_size(self):
        with self.assertRaises(ValueError):validate_file('x.pdf',b'\0'*(1024*1024+1),max_mb=1)

class StaticChecks(unittest.TestCase):
    def test_python_syntax(self):
        for f in ROOT.glob('*.py'):compile(f.read_text(),str(f),'exec')
    def test_no_live_secrets(self):
        self.assertFalse((ROOT/'.streamlit/secrets.toml').exists())
        self.assertIn('student_data_approved = false',(ROOT/'.streamlit/secrets.toml.example').read_text())
    def test_no_public_bucket(self):
        sql=(ROOT/'supabase/schema.sql').read_text()
        self.assertIn("'classroom-files','classroom-files',false",sql)
    def test_teacher_only_sensitive_tables(self):
        sql=(ROOT/'supabase/schema.sql').read_text()
        self.assertNotIn('create policy app_self on public.moods',sql)
        self.assertNotIn('create policy app_self on public.observations',sql)
        self.assertIn('and not p.must_change_password and not c.locked',sql)
    def test_feedback_private_in_shared_task(self):
        sql=(ROOT/'supabase/schema.sql').read_text()
        self.assertIn('s.id=submission_id and s.user_id=auth.uid()',sql)
    def test_service_only_login_rpcs(self):
        sql=(ROOT/'supabase/schema.sql').read_text()
        self.assertIn("f.name not in ('app_login_try','app_login_clear','app_password_changed')",sql)

if __name__=='__main__':unittest.main()
