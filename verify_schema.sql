-- schema.sql 실행 후 구조만 확인합니다. 실제 학생별 접근 실험을 대체하지 않습니다.
select '15개 테이블 RLS 활성' as check_name,
 (select count(*)=15 and bool_and(relrowsecurity)
 from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='public' and c.relname in
 ('classrooms','profiles','site_settings','materials','assignments','submissions','feedback',
 'questions','moods','presence','observations','points','notifications','layouts','login_throttle')) as passed
union all
select '파일 버킷 비공개',coalesce((select not public from storage.buckets where id='classroom-files'),false)
union all
select '미로그인 사용자의 교사 함수 호출 금지',not has_function_privilege('anon','public.app_is_teacher()','execute')
union all
select '학생의 로그인 제한 관리 함수 호출 금지',not has_function_privilege('authenticated','public.app_login_try(text)','execute')
union all
select '비밀번호 변경 트리거',exists(select 1 from pg_trigger where tgname='app_password_changed' and not tgisinternal)
union all
select '학생의 일반 프로필 수정 정책 없음',not exists(select 1 from pg_policies
 where schemaname='public' and tablename='profiles' and cmd in ('UPDATE','ALL') and policyname<>'app_teacher');
