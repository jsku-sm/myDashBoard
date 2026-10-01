-- 구쌤 수업 대시보드 v1.0 / 새 Supabase 프로젝트의 SQL Editor에서 실행
-- 기존 수업 데이터는 지우지 않습니다. public.app_* 함수와 이 앱의 정책을 재정의합니다.
begin;
create table if not exists public.classrooms (
 id text primary key check (id in ('1-1','1-2','1-3','1-4','1-5','1-6','1-7')),
 locked boolean not null default false,
 current_session uuid not null default gen_random_uuid(),
 session_title text not null default '수업 시작 전',
 subject text not null default '공통수학2',
 session_open boolean not null default false,
 started_at timestamptz not null default now()
);
insert into public.classrooms(id) select '1-'||i from generate_series(1,7) i on conflict do nothing;
create table if not exists public.profiles (
 id uuid primary key references auth.users(id) on delete cascade,
 student_id text unique not null,
 full_name text not null check(length(full_name) between 1 and 40),
 class_id text references public.classrooms(id),
 role text not null default 'student' check(role in ('student','teacher')),
 active boolean not null default true,
 must_change_password boolean not null default true,
 created_at timestamptz not null default now(),
 check(role='teacher' or (class_id is not null and student_id ~ '^10[1-7][0-9]{2}$'))
);
create table if not exists public.site_settings (
 id integer primary key default 1 check(id=1),
 content jsonb not null default '{}'::jsonb,
 updated_at timestamptz not null default now()
);
insert into public.site_settings(id) values(1) on conflict do nothing;
create table if not exists public.materials (
 id uuid primary key default gen_random_uuid(), subject text not null,
 unit text not null, title text not null check(length(title) between 1 and 150),
 kind text not null check(kind in ('평가계획','학습지','보충자료')),
 description text not null default '', class_id text references public.classrooms(id),
 path text unique not null, filename text not null, mime text not null,
 created_at timestamptz not null default now()
);
create table if not exists public.assignments (
 id uuid primary key default gen_random_uuid(), subject text not null, unit text not null,
 class_id text not null references public.classrooms(id),
 title text not null check(length(title) between 1 and 150), instructions text not null default '',
 rubric text not null default '', shared boolean not null default false,
 ai_enabled boolean not null default false, closed boolean not null default false,
 due_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.submissions (
 id uuid primary key default gen_random_uuid(),
 assignment_id uuid not null references public.assignments(id) on delete cascade,
 user_id uuid not null references public.profiles(id),
 note text not null default '' check(length(note)<=5000),
 ai_consent boolean not null default false,
 path text unique not null, filename text not null, mime text not null,
 created_at timestamptz not null default now()
);
create table if not exists public.feedback (
 id uuid primary key default gen_random_uuid(),
 submission_id uuid not null references public.submissions(id) on delete cascade,
 source text not null check(source in ('teacher','ai','system')),
 body text not null, created_at timestamptz not null default now()
);
create table if not exists public.questions (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references public.profiles(id),
 class_id text not null references public.classrooms(id), subject text not null, unit text not null,
 body text not null check(length(body) between 1 and 5000),
 shared boolean not null default false, answer text not null default '',
 created_at timestamptz not null default now(), answered_at timestamptz
);
create table if not exists public.moods (
 user_id uuid not null references public.profiles(id) on delete cascade,
 session_id uuid not null, class_id text not null references public.classrooms(id),
 value text not null check(value in ('happy','calm','neutral','tired','worried','frustrated','skip')),
 updated_at timestamptz not null default now(), primary key(user_id,session_id)
);
create table if not exists public.presence (
 user_id uuid not null references public.profiles(id) on delete cascade,
 session_id uuid not null, class_id text not null references public.classrooms(id),
 joined_at timestamptz not null default now(), last_seen timestamptz not null default now(),
 online boolean not null default true,
 primary key(user_id,session_id)
);
alter table public.presence add column if not exists online boolean not null default true;
create table if not exists public.observations (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id),
 class_id text not null references public.classrooms(id), observed_on date not null default current_date,
 subject text not null default '공통수학2', category text not null default '사고·성장',
 body text not null check(length(body) between 1 and 10000),
 teacher_id uuid not null references public.profiles(id), created_at timestamptz not null default now()
);
create table if not exists public.points (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id),
 class_id text not null references public.classrooms(id),
 delta integer not null check(delta between -100 and 100 and delta<>0),
 reason text not null check(length(reason) between 1 and 500),
 teacher_id uuid not null references public.profiles(id),
 cancelled boolean not null default false, cancel_reason text,
 created_at timestamptz not null default now()
);
create table if not exists public.notifications (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
 kind text not null check(kind in ('merit','demerit','feedback','info')),
 body text not null, seen_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.layouts (
 class_id text primary key references public.classrooms(id), rows integer not null check(rows between 1 and 10),
 cols integer not null check(cols between 1 and 10), entries jsonb not null default '[]'::jsonb,
 updated_at timestamptz not null default now()
);
create table if not exists public.login_throttle (
 fingerprint text primary key, failures integer not null default 1, window_start timestamptz not null default now()
);
create index if not exists idx_assignments_class on public.assignments(class_id,subject);
create index if not exists idx_submissions_assignment on public.submissions(assignment_id,user_id);
create index if not exists idx_feedback_submission on public.feedback(submission_id);
create index if not exists idx_presence_session on public.presence(class_id,session_id);
create index if not exists idx_moods_session on public.moods(class_id,session_id);
create index if not exists idx_notifications_unseen on public.notifications(user_id) where seen_at is null;
create index if not exists idx_points_student on public.points(user_id,created_at);
create index if not exists idx_observations_class on public.observations(class_id,observed_on);

-- SECURITY DEFINER helpers never accept a caller-supplied user ID for authorisation.
create or replace function public.app_is_teacher() returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.profiles where id=auth.uid() and role='teacher' and active)
$$;
create or replace function public.app_my_class() returns text
language sql stable security definer set search_path='' as $$
 select class_id from public.profiles where id=auth.uid() and active
$$;
create or replace function public.app_can_work() returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.profiles p join public.classrooms c on p.class_id=c.id
 where p.id=auth.uid() and p.role='student' and p.active and not p.must_change_password and not c.locked)
$$;
create or replace function public.app_can_read_submission(sid uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select public.app_is_teacher() or (public.app_can_work() and exists(
 select 1 from public.submissions s join public.assignments a on s.assignment_id=a.id
 where s.id=sid and a.class_id=public.app_my_class() and (s.user_id=auth.uid() or a.shared)))
$$;
create or replace function public.app_can_read_file(object_name text) returns boolean
language sql stable security definer set search_path='' as $$
 select public.app_is_teacher() or (public.app_can_work() and (
 exists(select 1 from public.materials m where m.path=object_name and (m.class_id is null or m.class_id=public.app_my_class()))
 or exists(select 1 from public.submissions s join public.assignments a on a.id=s.assignment_id
 where s.path=object_name and a.class_id=public.app_my_class() and (s.user_id=auth.uid() or a.shared))))
$$;
create or replace function public.app_can_upload_file(object_name text) returns boolean
language sql stable security definer set search_path='' as $$
 select public.app_is_teacher() or (public.app_can_work()
 and split_part(object_name,'/',1)='submissions' and split_part(object_name,'/',2)=auth.uid()::text
 and exists(select 1 from public.assignments a where a.id::text=split_part(object_name,'/',3)
 and a.class_id=public.app_my_class() and not a.closed))
$$;

-- Password-change trigger: students cannot directly clear the first-login flag.
create or replace function public.app_password_changed() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if new.encrypted_password is distinct from old.encrypted_password then
   update public.profiles set must_change_password=false where id=new.id;
 end if;
 return new;
end $$;
drop trigger if exists app_password_changed on auth.users;
create trigger app_password_changed after update of encrypted_password on auth.users
for each row execute function public.app_password_changed();

-- One compact server round trip for presence, lock and pending notification state.
create or replace function public.app_poll() returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.profiles; c public.classrooms; pending integer;
begin
 select * into p from public.profiles where id=auth.uid();
 if p.id is null or not p.active then raise exception 'AUTH_REQUIRED'; end if;
 if p.role='teacher' then return jsonb_build_object('teacher',true); end if;
 select * into c from public.classrooms where id=p.class_id;
 if not p.must_change_password then
  insert into public.presence(user_id,session_id,class_id) values(p.id,c.current_session,p.class_id)
  on conflict(user_id,session_id) do update set last_seen=now(),online=true
  where public.presence.last_seen < now()-interval '20 seconds' or not public.presence.online;
 end if;
 select count(*) into pending from public.notifications where user_id=p.id and seen_at is null;
 return jsonb_build_object('locked',c.locked,'session_id',c.current_session,'session_title',c.session_title,
  'session_open',c.session_open,'must_change_password',p.must_change_password,
  'pending',case when c.locked or p.must_change_password then 0 else pending end);
end $$;
create or replace function public.app_set_mood(mood text) returns void
language plpgsql security definer set search_path='' as $$
declare c public.classrooms;
begin
 if not public.app_can_work() then raise exception 'LOCKED_OR_FORBIDDEN'; end if;
 select * into c from public.classrooms where id=public.app_my_class();
 insert into public.moods(user_id,session_id,class_id,value) values(auth.uid(),c.current_session,c.id,mood)
 on conflict(user_id,session_id) do update set value=excluded.value,updated_at=now();
end $$;
create or replace function public.app_mark_notice(notice uuid) returns boolean
language plpgsql security definer set search_path='' as $$
begin
 if not public.app_can_work() then raise exception 'LOCKED_OR_FORBIDDEN'; end if;
 update public.notifications set seen_at=now() where id=notice and user_id=auth.uid() and seen_at is null;
 return found;
end $$;
create or replace function public.app_logout() returns void
language plpgsql security definer set search_path='' as $$
begin
 -- Sign-out connection hint; this is not an attendance record.
 update public.presence set online=false,last_seen=now() where user_id=auth.uid()
 and session_id=(select current_session from public.classrooms where id=public.app_my_class());
end $$;
create or replace function public.app_start_class(target_class text, lesson_title text, lesson_subject text) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not public.app_is_teacher() then raise exception 'FORBIDDEN'; end if;
 update public.classrooms set current_session=gen_random_uuid(), session_title=left(lesson_title,150),
  subject=lesson_subject,session_open=true,locked=false,started_at=now() where id=target_class;
end $$;
create or replace function public.app_award_points(target_user uuid, amount integer, why text) returns void
language plpgsql security definer set search_path='' as $$
declare p public.profiles;
begin
 if not public.app_is_teacher() then raise exception 'FORBIDDEN'; end if;
 select * into p from public.profiles where id=target_user and role='student' and active;
 if p.id is null then raise exception 'STUDENT_NOT_FOUND'; end if;
 insert into public.points(user_id,class_id,delta,reason,teacher_id)
 values(p.id,p.class_id,amount,why,auth.uid());
 insert into public.notifications(user_id,kind,body) values(p.id,
 case when amount>0 then 'merit' else 'demerit' end,
 case when amount>0 then '상점 ' else '벌점 ' end||abs(amount)::text||'점 · '||why);
end $$;
create or replace function public.app_cancel_points(point_id uuid, why text) returns void
language plpgsql security definer set search_path='' as $$
declare p public.points;
begin
 if not public.app_is_teacher() then raise exception 'FORBIDDEN'; end if;
 if length(trim(why))=0 then raise exception 'REASON_REQUIRED'; end if;
 update public.points set cancelled=true,cancel_reason=why where id=point_id and not cancelled returning * into p;
 if p.id is not null then
 insert into public.notifications(user_id,kind,body) values(p.user_id,'info','상벌점 정정: '||p.reason||' / 정정 사유: '||why);
 end if;
end $$;
create or replace function public.app_purge_transient(target_class text, cutoff timestamptz) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not public.app_is_teacher() or cutoff>=now() then raise exception 'FORBIDDEN_OR_BAD_DATE'; end if;
 delete from public.moods where class_id=target_class and updated_at<cutoff
 and session_id<>(select current_session from public.classrooms where id=target_class);
 delete from public.presence where class_id=target_class and last_seen<cutoff
 and session_id<>(select current_session from public.classrooms where id=target_class);
 delete from public.notifications where created_at<cutoff and seen_at is not null
 and user_id in(select id from public.profiles where class_id=target_class);
end $$;
-- Server-only throttling: no unauthenticated table read is permitted.
create or replace function public.app_login_try(key_hash text) returns boolean
language plpgsql security definer set search_path='' as $$
declare n integer;
begin
 insert into public.login_throttle(fingerprint) values(key_hash)
 on conflict(fingerprint) do update set
 failures=case when public.login_throttle.window_start<now()-interval '10 minutes' then 1 else public.login_throttle.failures+1 end,
 window_start=case when public.login_throttle.window_start<now()-interval '10 minutes' then now() else public.login_throttle.window_start end
 returning failures into n;
 return n<=10;
end $$;
create or replace function public.app_login_clear(key_hash text) returns void
language sql security definer set search_path='' as $$
 delete from public.login_throttle where fingerprint=key_hash
$$;

-- Explicit privileges + RLS. No anonymous access and no student profile mutation.
do $$ declare t text; begin
 foreach t in array array['classrooms','profiles','site_settings','materials','assignments','submissions','feedback',
 'questions','moods','presence','observations','points','notifications','layouts','login_throttle'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('revoke all on public.%I from anon,authenticated',t);
 execute format('grant select,insert,update,delete on public.%I to authenticated,service_role',t);
 execute format('drop policy if exists app_teacher on public.%I',t);
 if t <> 'login_throttle' then
 execute format('create policy app_teacher on public.%I for all to authenticated using(public.app_is_teacher()) with check(public.app_is_teacher())',t);
 end if;
 end loop;
end $$;
drop policy if exists app_self on public.profiles;
create policy app_self on public.profiles for select to authenticated using(id=auth.uid() and active);
drop policy if exists app_class on public.classrooms;
create policy app_class on public.classrooms for select to authenticated using(id=public.app_my_class());
drop policy if exists app_settings on public.site_settings;
create policy app_settings on public.site_settings for select to authenticated using(public.app_can_work());
drop policy if exists app_materials on public.materials;
create policy app_materials on public.materials for select to authenticated
using(public.app_can_work() and (class_id is null or class_id=public.app_my_class()));
drop policy if exists app_assignments on public.assignments;
create policy app_assignments on public.assignments for select to authenticated
using(public.app_can_work() and class_id=public.app_my_class());
drop policy if exists app_read_submissions on public.submissions;
create policy app_read_submissions on public.submissions for select to authenticated using(public.app_can_read_submission(id));
drop policy if exists app_submit on public.submissions;
create policy app_submit on public.submissions for insert to authenticated with check(
 public.app_can_work() and user_id=auth.uid() and public.app_can_upload_file(path)
 and split_part(path,'/',3)=assignment_id::text
 and exists(select 1 from public.assignments a where a.id=assignment_id and a.class_id=public.app_my_class() and not a.closed));
drop policy if exists app_feedback on public.feedback;
create policy app_feedback on public.feedback for select to authenticated using(public.app_can_work()
 and exists(select 1 from public.submissions s where s.id=submission_id and s.user_id=auth.uid()));
-- Even when an assignment is shared, feedback remains private to its owner and teachers.
drop policy if exists app_read_questions on public.questions;
create policy app_read_questions on public.questions for select to authenticated using(
 public.app_can_work() and class_id=public.app_my_class() and (user_id=auth.uid() or shared));
drop policy if exists app_ask on public.questions;
create policy app_ask on public.questions for insert to authenticated with check(
 public.app_can_work() and user_id=auth.uid() and class_id=public.app_my_class() and answer='' and answered_at is null);
drop policy if exists app_points on public.points;
create policy app_points on public.points for select to authenticated using(public.app_can_work() and user_id=auth.uid());
drop policy if exists app_notices on public.notifications;
create policy app_notices on public.notifications for select to authenticated using(public.app_can_work() and user_id=auth.uid());
-- moods/presence/layouts/observations: teacher policies only. Students use controlled RPCs.

-- Only private objects. No public bucket, no persistent signed links in this application.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('classroom-files','classroom-files',false,20971520,array['application/pdf','image/jpeg','image/png'])
on conflict(id) do update set public=false,file_size_limit=20971520,
allowed_mime_types=array['application/pdf','image/jpeg','image/png'];
drop policy if exists app_files_read on storage.objects;
create policy app_files_read on storage.objects for select to authenticated
using(bucket_id='classroom-files' and public.app_can_read_file(name));
drop policy if exists app_files_insert on storage.objects;
create policy app_files_insert on storage.objects for insert to authenticated
with check(bucket_id='classroom-files' and public.app_can_upload_file(name));
drop policy if exists app_files_update on storage.objects;
create policy app_files_update on storage.objects for update to authenticated
using(bucket_id='classroom-files' and public.app_is_teacher())
with check(bucket_id='classroom-files' and public.app_is_teacher());
drop policy if exists app_files_delete on storage.objects;
create policy app_files_delete on storage.objects for delete to authenticated
using(bucket_id='classroom-files' and public.app_is_teacher());

-- Revoke PostgreSQL's default PUBLIC execute privilege on app functions.
do $$ declare f record; begin
 for f in select p.oid::regprocedure as signature,p.proname as name from pg_proc p
 join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'app\_%' escape '\' loop
 execute format('revoke all on function %s from public,anon,authenticated',f.signature);
 execute format('grant execute on function %s to service_role',f.signature);
 if f.name not in ('app_login_try','app_login_clear','app_password_changed') then
 execute format('grant execute on function %s to authenticated',f.signature);
 end if;
 end loop;
end $$;
commit;
