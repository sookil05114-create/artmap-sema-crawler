# Dedup 결정 리포트

- 입력 신규 venue: **130곳**
- daily 크롤러 처리 대상 (sema/mmca) → 제외: **3곳**
- 기존(gallery_crawler + craft_museum_crawler)과 중복 → 제외: **21곳**
- 신규 내부 중복 → 제외: **2곳**
- 최종 신규 추가: **104곳**

## daily 크롤러 처리 대상 (별도 워크플로우)

- 국립현대미술관 서울관 — sema_daily.yml (SeMA/MMCA crawler)에서 별도 처리
- 서울시립미술관 서소문본관 — sema_daily.yml (SeMA/MMCA crawler)에서 별도 처리
- 국립현대미술관 덕수궁관 — sema_daily.yml (SeMA/MMCA crawler)에서 별도 처리

## 기존과 중복 (신규에서 제외)

| 신규 이름 | 기존 venue_key | 매칭 근거 | 검증 결과로 보완 가능한 필드 |
|---|---|---|---|
| 서울미술관 | `seoul_museum_seokpajeong` | domain=seoulmuseum.org, name_match | address=서울 종로구 창의문로11길 4-1 (부암동, 석파정), phone=02-395-0100, email=info@seoulmuseum.org, hours=10:00~18:00(수-금), exhibit_channel=인스타 |
| 아트선재센터 | `artsonje_center` | domain=artsonje.org, name_match | address=서울 종로구 율곡로3길 87 (소격동), phone=02-733-8949, email=info@artsonje.org, hours=12:00~18:00(화-일), exhibit_channel=인스타 |
| 일민미술관 | `ilmin_museum` | domain=ilmin.org, name_match | address=서울 종로구 세종대로 152 (동아일보사옥), phone=02-2020-2050, email=info@ilmin.org, hours=11:00~19:00(화-일), exhibit_channel=홈페이지 |
| 서울공예박물관 | `seoul_craft_museum` | domain=craftmuseum.seoul.go.kr, name_match | address=서울 종로구 율곡로3길 4, phone=02-6450-7000, email=scmuseum@seoul.go.kr, hours=10:00~18:00(화-일), exhibit_channel=홈페이지 |
| 두산갤러리 서울 | `euljiro_doosanartcenter_gallery` | insta=doosanartcenter_gallery | address=서울 종로구 종로33길 15 (연건동), phone=02-708-5050, email=doosangallery@doosan.com, hours=11:00~19:00(화-토), exhibit_channel=홈페이지 |
| 상업화랑 을지로 | `euljiro_sahngupgallery` | insta=sahngupgallery, domain=sahngupgallery.com, name_match, alias_match | address=서울 중구 을지로 143 4층, phone=02-794-2226, email=sahnggub@gmail.com, hours=13:00~19:00(화-금), 13:00~18:00(..., exhibit_channel=인스타 |
| 더 소소 | `euljiro_gallerysoso` | insta=gallerysoso_, name_match, alias_match | address=서울 중구 청계천로 172-1 4-5층, phone=02-2277-8154, email=info@gallerysoso.com, hours=13:00~18:00(화-토), exhibit_channel=인스타 |
| 플로우앤비트 | `euljiro_flow_n_beat` | insta=flow.n.beat, name_match, alias_match | address=서울 중구 동호로 385-2, phone=031-949-8154, email=flowandbeat@gmail.com, hours=13:00~18:00(수-토), 13:00~17:00(..., exhibit_channel=인스타 |
| 에케이다 | `euljiro_eckeida` | insta=eckeida, name_match, alias_match | address=서울 중구 퇴계로39길 12-7 1층, phone=0507-1312-3574, email=eckeida@gmail.com, hours=13:00~18:00(수-일), exhibit_channel=인스타 |
| 시각미술연구소 필승사 | `euljiro_pilseungsa_art` | insta=pilseungsa.art, name_match | address=서울 종로구 청계천로 159 . 가동 라열 435호, phone=010-4366-5918, email=pilseungsa.art@gmail.com, hours=10:00~다음날 7:00, exhibit_channel=인스타 |
| 스페이스카다로그 | `euljiro_cadalogs_space` | insta=cadalogs_space, name_match, alias_match | address=서울 중구 수표로 58-1 3층, phone=0507-1382-1868, email=cadalogs.space@gmail.com, hours=13:00~19:00(화-금), 13:00~18:00(..., exhibit_channel=인스타 |
| 디휘테 갤러리 | `euljiro_die_huette_gallery` | insta=die_huette_gallery, name_match, alias_match | address=서울 중구 마른내로12길 7-11 2층, email=diehuette.gallery@gmail.com, hours=11:00~18:00(월-토), exhibit_channel=인스타 |
| 스페이스유닛+ | `euljiro_space_unit_plus` | insta=space.unit_plus, name_match, alias_match | address=서울 중구 을지로 143, phone=010-7301-0730, email=space.unit@gmail.com, hours=13:00~18:00(수-토), exhibit_channel=인스타 |
| 그블루갤러리 | `euljiro_gblue_gallery` | insta=gblue_gallery, name_match, alias_match | address=서울 중구 충무로5길 2 3층 302호, phone=0507-1339-3704, email=gblue.gallery@gmail.com, hours=13:00~19:00(수-일), exhibit_channel=인스타 |
| 갤러리 SoSo- 을지로 | `euljiro_gallerysoso` | insta=gallerysoso_ | address=서울 중구 청계천로 172-1 4-5층, phone=02-2277-8154, email=info@gallerysoso.com, hours=13:00~18:00(수-일), exhibit_channel=인스타 |
| YPC스페이스 | `euljiro_ypc_seoul` | insta=ypc.seoul, name_match, alias_match | address=서울 중구 퇴계로 258, email=ypc.seoul@gmail.com, hours=전시 및 프로그램별 공지, exhibit_channel=홈페이지 |
| YK Presents | `euljiro_yk_presents` | insta=yk_presents, name_match | address=서울 중구 을지로43길 13, phone=010-6729-0405, email=yk.presents@gmail.com, hours=13:00~18:00(화-토), exhibit_channel=인스타 |
| PS센터 | `euljiro_p_s_center` | insta=p.s.center, name_match, alias_match | address=서울 중구 창경궁로5다길 18, phone=02-6956-3501, email=p.s.center.seoul@gmail.com, hours=11:00~18:00(화-토), exhibit_channel=인스타 |
| N/A 갤러리 | `euljiro_nslasha_kr` | insta=nslasha.kr, domain=nslasha.kr | address=서울 중구 창경궁로5길 27, phone=070-7778-7222, email=nslasha.kr@gmail.com, hours=12:00~19:00(화-토) 14:00~19:00(일..., exhibit_channel=인스타 |
| COSO | `euljiro_coso_seoul` | insta=coso_seoul, name_match, alias_match | address=서울 중구 창경궁로5길 32 3층(산림동), phone=010-3291-1535, email=coso.seoul@gmail.com, hours=13:00~19:00 (전시마다 휴무 다름), exhibit_channel=인스타 |
| 갤러리모스 | `euljiro_gallerymos_official` | insta=gallerymos.official, name_match, alias_match | address=서울 중구 을지로 138 1층, phone=0507-1360-0999, email=gallerymos.official@gmail.com, hours=11:00~20:00(화-일), exhibit_channel=인스타 |

> 💡 이 21곳의 알바 검증 정보 (주소/전화/이메일/운영시간/전시갱신채널)는 기존 venues.json에 부분 보완할 수 있습니다. 별도 PR로 따로 작업 권장.

## 신규 내부 중복 (제거)

| 유지 | 제거 | 이유 |
|---|---|---|
| PKM 갤러리 | PKM 갤러리 강남 (verified) | 동일 subregion + insta @pkmgallery + 동일 주소 |
| 오페라갤러리 | 오페라갤러리 서울 (pending) | 동일 subregion + insta @operagallery + 동일 주소 |

## 최종 venue_key 목록 (권역 접두어 적용)

### gangnam (25곳)

- `gangnam_perrotin_seoul` — 페로탕
- `gangnam_gallery_planet` — 갤러리 플래닛
- `gangnam_gallery_now` — 갤러리나우
- `gangnam_maiateumyujieom` — 마이아트뮤지엄
- `gangnam_yuminateumyujieom` — 유민아트뮤지엄
- `gangnam_horimbakmulgwan_sinsabungwan` — 호림박물관 신사분관
- `gangnam_songeun` — 송은
- `gangnam_johyeonhwarang_seoul` — 조현화랑 서울
- `gangnam_joseonhwarang` — 조선화랑
- `gangnam_gaelreorisein` — 갤러리세인
- `gangnam_yuateuseupeiseu` — 유아트스페이스
- `gangnam_gaelreoripichi` — 갤러리피치
- `gangnam_gimriagaelreori` — 김리아갤러리
- `gangnam_operagaelreori` — 오페라갤러리
- `gangnam_oeioeigaelreori` — 오에이오에이갤러리
- `gangnam_iyujingaelreori` — 이유진갤러리
- `gangnam_313_art_project` — 313 ART PROJECT
- `gangnam_beuraungaelreori` — 브라운갤러리
- `gangnam_poseukomisulgwan` — 포스코미술관
- `gangnam_ggaelreori` — G갤러리
- `gangnam_igirigugaelreori` — 이길이구갤러리
- `gangnam_lina_gallery` — 리나갤러리
- `gangnam_tang_contemporary_art` — 탕 컨템포러리 아트
- `gangnam_seupeiseuk_seoul` — 스페이스K 서울
- `gangnam_hideunemgaelreori` — 히든엠갤러리

### jongno (63곳)

- `jongno_seoulsirip_misurakaibeu` — 서울시립 미술아카이브
- `jongno_ocimisulgwan` — OCI미술관
- `jongno_hakgojae` — 학고재
- `jongno_gaelreorihyeondae` — 갤러리현대
- `jongno_pkm_gaelreori` — PKM 갤러리
- `jongno_gwanhungaelreori` — 관훈갤러리
- `jongno_jaedanbeobin_yeol_yeolbukchonga` — 재단법인 예올 / 예올북촌가
- `jongno_barakat` — 바라캇 컨템포러리
- `jongno_ihwaikgaelreori` — 이화익갤러리
- `jongno_nohwarang` — 노화랑
- `jongno_sun_gallery` — 선화랑
- `jongno_myujieomhanmi_samcheong` — 뮤지엄한미 삼청
- `jongno_arariogaelreori_seoul` — 아라리오갤러리 서울
- `jongno_simyoart` — 심여화랑
- `jongno_gaelreorijinseon` — 갤러리진선
- `jongno_gaelreoriijeu` — 갤러리이즈
- `jongno_gaelreoriateuringkeu` — 갤러리아트링크
- `jongno_imokhwarang` — 이목화랑
- `jongno_tonginhwarang` — 통인화랑
- `jongno_gaelreorisimon` — 갤러리시몬
- `jongno_yehwarang` — 예화랑
- `jongno_gaelreorisejul` — 갤러리세줄
- `jongno_gaelreoribaum` — 갤러리바움
- `jongno_gaelreorimijeu` — 갤러리미즈
- `jongno_topohauseu_ateusenteo` — 토포하우스 아트센터
- `jongno_dongsanbanghwarang` — 동산방화랑
- `jongno_jangeunseongaelreori` — 장은선갤러리
- `jongno_baik_art` — 백아트
- `jongno_choi_choi` — 초이앤초이갤러리
- `jongno_nook` — 누크갤러리
- `jongno_songwonateusenteo` — 송원아트센터
- `jongno_gonggeunhyegaelreori` — 공근혜갤러리
- `jongno_291potogeuraepseu` — 291포토그랩스
- `jongno_gaelreoriramereu` — 갤러리라메르
- `jongno_gaelreoridam` — 갤러리담
- `jongno_arko` — 아르코미술관
- `jongno_hwangimisulgwan` — 환기미술관
- `jongno_totalmisulgwan` — 토탈미술관
- `jongno_jongromunhwajaedan` — 종로문화재단
- `jongno_jahamisulgwan` — 자하미술관
- `jongno_arariomyujieom_in_seupeiseu` — 아라리오뮤지엄 인 스페이스
- `jongno_hanbyeogwonmisulgwan` — 한벽원미술관
- `jongno_geumhomisulgwan` — 금호미술관
- `jongno_gimjongyeongmisulgwan` — 김종영미술관
- `jongno_seongbukdong_gansongmisulgwan` — 성북동 간송미술관
- `jongno_seonggokmisulgwan` — 성곡미술관
- `jongno_boan1942` — 보안1942
- `jongno_jjjungjeonggaelreori` — JJ중정갤러리
- `jongno_gaelreori_kiche` — 갤러리 KICHE
- `jongno_gaelreori_geurimson` — 갤러리 그림손
- `jongno_doll` — 갤러리 도올
- `jongno_hakgojae_ateusenteo` — 학고재 아트센터
- `jongno_garamhwarang` — 가람화랑
- `jongno_ganaateusenteo` — 가나아트센터
- `jongno_wolhamisul` — 월하미술
- `jongno_a_lounge` — 에이라운지 갤러리
- `jongno_gaelreoribarakat_seoul` — 갤러리바라캇 서울
- `jongno_page_room_8` — 페이지룸8
- `jongno_insaateusenteo` — 인사아트센터
- `jongno_pyogaelreori` — 표갤러리
- `jongno_sehwamisulgwan` — 세화미술관
- `jongno_horiateuseupeiseu` — 호리아트스페이스
- `jongno_olmiateuseupeiseu` — 올미아트스페이스

### junggu (6곳)

- `junggu_jungganjijeom_hana_dul` — 중간지점 하나 / 둘
- `junggu_iruseupeiseu` — 일우스페이스
- `junggu_deoksugung_seokjojeon_daehanjegugyeoksagwan` — 덕수궁 석조전 대한제국역사관
- `junggu_seonggonghoe_jeongdong1928ateusenteo` — 성공회 정동1928아트센터
- `junggu_ddp` — 동대문디자인플라자
- `junggu_piknic` — 피크닉

### seocho (4곳)

- `seocho_yesuruijeondang_hangarammisulgwan` — 예술의전당 한가람미술관
- `seocho_yesuruijeondang_hangaramdijainmisulgwan` — 예술의전당 한가람디자인미술관
- `seocho_saemteohwarang` — 샘터화랑
- `seocho_space_isu` — 스페이스이수

### seongdong (2곳)

- `seongdong_atelier_aki` — 아뜰리에 아키
- `seongdong_d_gallery` — 더페이지갤러리

### yongsan (4곳)

- `yongsan_gaelreorisinra_seoul` — 갤러리신라 서울
- `yongsan_lehmann_maupin` — 리만머핀 서울
- `yongsan_bhak` — BHAK
- `yongsan_gaelreorierd` — 갤러리ERD
