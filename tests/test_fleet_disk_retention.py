import unittest,tempfile,pathlib,os,time,json
from unittest.mock import patch,Mock
from ops import fleet_disk_retention as m

class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  for name in ("repository_busy","container_mount_overlap"):
   mock=patch.object(m,name,return_value=False);mock.start();self.addCleanup(mock.stop)
 def tearDown(self):self.tmp.cleanup()
 def cache(self):
  p=self.root/'node_modules';p.mkdir();(p/'a.js').write_text('old');(self.root/'package-lock.json').write_text('{}')
  return p
 def test_unknown_resource_is_preserved(self):
  p=self.cache()
  with patch.object(m,'CONFIG',{'cache_roots':[]}):
   self.assertEqual(m.remove_cache(p),'SKIP_SCOPE')
  self.assertTrue(p.exists())
 def test_external_symlink_is_preserved(self):
  p=self.cache();(self.root/'valuable').write_text('v');(p/'x').symlink_to(self.root/'valuable')
  with patch.object(m.guard,'CUTOFF',float('inf')),patch.object(m.guard,'open_file',return_value=False),patch.object(m.guard,'mount_points',return_value=set()):
   self.assertFalse(m.safe_cache(p))
 def test_internal_links_can_be_evicted(self):
  p=self.cache();(p/'x').symlink_to('a.js');os.link(p/'a.js',p/'hard')
  with patch.object(m.guard,'CUTOFF',float('inf')),patch.object(m.guard,'open_file',return_value=False),patch.object(m.guard,'mount_points',return_value=set()):
   self.assertTrue(m.safe_cache(p))
 def test_external_hardlink_is_preserved(self):
  p=self.cache();os.link(p/'a.js',self.root/'outside')
  with patch.object(m.guard,'CUTOFF',float('inf')),patch.object(m.guard,'open_file',return_value=False),patch.object(m.guard,'mount_points',return_value=set()):
   self.assertFalse(m.safe_cache(p))
 def test_fresh_descendant_is_preserved(self):
  p=self.cache()
  with patch.object(m.guard,'open_file',return_value=False),patch.object(m.guard,'mount_points',return_value=set()):
   self.assertFalse(m.safe_cache(p))
 def test_open_file_and_bind_mount_block_cleanup(self):
  p=self.cache()
  with patch.object(m.guard,'CUTOFF',float('inf')),patch.object(m.guard,'open_file',return_value=True),patch.object(m.guard,'mount_points',return_value=set()):
   self.assertFalse(m.safe_cache(p))
  with patch.object(m.guard,'CUTOFF',float('inf')),patch.object(m.guard,'open_file',return_value=False),patch.object(m.guard,'mount_points',return_value={p/'bind'}):
   self.assertFalse(m.safe_cache(p))
 def test_active_log_name_is_never_eligible(self):
  self.assertFalse(m.log_allowed(pathlib.Path('/var/log/syslog')))
  self.assertFalse(m.log_allowed(pathlib.Path('/var/log/auth.log')))
  self.assertFalse(m.log_allowed(pathlib.Path('/var/log/wtmp')))
  self.assertFalse(m.log_allowed(pathlib.Path('/var/log/nginx/customer.db.1')))
  self.assertTrue(m.log_allowed(pathlib.Path('/var/log/syslog.2.gz')))
  self.assertTrue(m.log_allowed(pathlib.Path('/var/log/x-ui/3xui-2026-10-07T08-38-16.613.log.gz')))
 def test_recent_rename_does_not_age_content_but_must_be_quiet(self):
  p=self.root/'syslog.2.gz';p.write_bytes(b'log')
  old=time.time()-10*86400;os.utime(p,(old,old))
  self.assertFalse(m.old_log(p)) # freshly created/renamed, still in one-hour quiet period
 def test_firewall_runtime_counters_and_bans_do_not_mask_static_changes(self):
  a='*filter\n:INPUT ACCEPT [10:200]\n:f2b-sshd - [0:0]\n-A INPUT -p tcp --dport 22 -j f2b-sshd\n-A f2b-sshd -s 192.0.2.1/32 -j REJECT --reject-with icmp-port-unreachable\n-A f2b-sshd -j RETURN\nCOMMIT'
  b=a.replace('[10:200]','[90:2000]').replace('192.0.2.1','192.0.2.2')
  self.assertEqual(m.firewall_base(a),m.firewall_base(b))
  self.assertNotEqual(m.firewall_base(a),m.firewall_base(b.replace('--dport 22','--dport 23')))
  self.assertNotEqual(m.firewall_base(a),m.firewall_base(b.replace('-j RETURN','-j ACCEPT')))
 def test_dry_run_never_mutates(self):
  healthy={'ok':True,'identity':{},'errors':[],'free':60,'total':100}
  with patch.object(m,'LOCK',self.root/'lock'),patch.object(m,'snapshot',return_value=healthy),patch.object(m,'plans',return_value=[('cache',self.root/'x')]),patch.object(m,'execute') as e,patch.object(m,'load_config',return_value={}):
   self.assertEqual(m.main([]),0);e.assert_not_called()
 def test_bad_health_aborts_apply(self):
  bad={'ok':False,'identity':{},'errors':['offline'],'free':60,'total':100}
  with patch.object(m,'LOCK',self.root/'lock'),patch.object(m,'snapshot',return_value=bad),patch.object(m,'load_config',return_value={}),patch.object(m,'audit'),patch.object(m,'execute') as e:
   self.assertEqual(m.main(['--apply']),2);e.assert_not_called()
 def test_changed_service_aborts_before_deletion(self):
  a={'ok':True,'identity':{'pid':1},'errors':[],'free':60,'total':100};b={**a,'identity':{'pid':2}}
  with patch.object(m,'LOCK',self.root/'lock'),patch.object(m,'snapshot',side_effect=[a,b,b]),patch.object(m,'load_config',return_value={}),patch.object(m,'audit'),patch.object(m,'plans',return_value=[('cache',self.root/'x')]),patch.object(m,'execute') as e:
   self.assertEqual(m.main(['--apply']),2);e.assert_not_called()
 def test_compression_preserves_exact_log_bytes(self):
  p=self.root/'syslog.1';data=b'completed log\n'*10000;p.write_bytes(data)
  with patch.object(m,'compress_allowed',return_value=True),patch.object(m,'quiet_file',return_value=True),patch.object(m.guard,'open_file',return_value=False),patch.object(m,'audit'):
   self.assertEqual(m.compress_log(p),'COMPRESSED')
  import gzip
  self.assertFalse(p.exists());self.assertEqual(gzip.open(str(p)+'.gz','rb').read(),data)
 def test_compression_never_overwrites_existing_archive(self):
  p=self.root/'syslog.1';p.write_bytes(b'log'*10000);gz=pathlib.Path(str(p)+'.gz');gz.write_bytes(b'precious')
  with patch.object(m,'compress_allowed',return_value=True),patch.object(m,'quiet_file',return_value=True):
   self.assertEqual(m.compress_log(p),'SKIP_EXISTING')
  self.assertEqual(gz.read_bytes(),b'precious');self.assertTrue(p.exists())

if __name__=='__main__':unittest.main()

class Provenance(unittest.TestCase):
 def test_owned_archive_tag_required(self):
  import io,tarfile
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp)/('a'*40);d.mkdir();p=d/('pv-growth-app-'+d.name+'.tar')
   def make(tag):
    with tarfile.open(p,'w') as t:
     data=json.dumps([{'RepoTags':['pv-growth-app:'+tag]}]).encode();info=tarfile.TarInfo('manifest.json');info.size=len(data);t.addfile(info,io.BytesIO(data))
   make('b'*40);self.assertFalse(m.growth_provenance(d))
   make(d.name);self.assertTrue(m.growth_provenance(d))
 def test_unknown_archive_directory_never_evicted(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp)/('a'*40);d.mkdir();(d/'customer.sql').write_text('customer records')
   self.assertFalse(m.growth_provenance(d))

class RestoreArchive(unittest.TestCase):
 def test_all_layers_and_config_must_match_installed_image(self):
  import io,tarfile,hashlib
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp)/'image.tar';tag='a'*40;layer=b'recoverable application layer'
   diff='sha256:'+hashlib.sha256(layer).hexdigest()
   cfg={'rootfs':{'diff_ids':[diff]},'config':{'Cmd':['app']}}
   manifest=[{'RepoTags':['pv-growth-app:'+tag],'Config':'config.json','Layers':['layer.tar']}]
   with tarfile.open(p,'w') as t:
    for name,data in [('manifest.json',json.dumps(manifest).encode()),('config.json',json.dumps(cfg).encode()),('layer.tar',layer)]:
     info=tarfile.TarInfo(name);info.size=len(data);t.addfile(info,io.BytesIO(data))
   actual=[{'RootFS':{'Layers':[diff]},'Config':{'Cmd':['app']}}]
   with patch.object(m,'checked',return_value=json.dumps(actual)),patch.object(m.guard,'open_file',return_value=False):
    self.assertTrue(m.archive_complete(p,tag))
   m.RESTORE_CACHE.clear()
   actual[0]['Config']['Cmd']=['different-app']
   with patch.object(m,'checked',return_value=json.dumps(actual)),patch.object(m.guard,'open_file',return_value=False):
    self.assertFalse(m.archive_complete(p,tag))

class AptScope(unittest.TestCase):
 def test_only_package_downloads_are_in_scope(self):
  self.assertTrue(m.apt_allowed(pathlib.Path('/var/cache/apt/archives/package_1.0_amd64.deb')))
  self.assertFalse(m.apt_allowed(pathlib.Path('/var/lib/dpkg/status')))
  self.assertFalse(m.apt_allowed(pathlib.Path('/var/cache/apt/archives/lock')))
  self.assertFalse(m.apt_allowed(pathlib.Path('/var/cache/apt/archives/partial/package.deb')))

class AptBusy(unittest.TestCase):
 def test_active_unattended_transaction_blocks_download_cleanup(self):
  from types import SimpleNamespace
  class Proc:
   name='999'
   def __truediv__(self,k):
    if k=='comm':return SimpleNamespace(read_text=lambda:'unattended-upgr')
    return SimpleNamespace(read_bytes=lambda:b'/usr/bin/python3\x00/usr/bin/unattended-upgrade\x00')
  with patch.object(m.pathlib.Path,'iterdir',return_value=[Proc()]):
   self.assertFalse(m.apt_idle())

class LazyUsage(unittest.TestCase):
 def test_parent_working_directory_and_host_bind_mount_block_cache_eviction(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp)/'node_modules';p.mkdir();(p/'package.js').write_text('code')
   with patch.object(m,'repository_busy',return_value=True),patch.object(m,'container_mount_overlap',return_value=False):
    self.assertFalse(m.safe_cache(p))
   with patch.object(m,'repository_busy',return_value=False),patch.object(m,'container_mount_overlap',return_value=True):
    self.assertFalse(m.safe_cache(p))

class RestoreCacheBinding(unittest.TestCase):
 def test_retagged_image_requires_revalidation_even_if_archive_unchanged(self):
  import io,tarfile,hashlib
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp)/'image.tar';tag='a'*40;layer=b'app';diff='sha256:'+hashlib.sha256(layer).hexdigest()
   cfg={'rootfs':{'diff_ids':[diff]},'config':{'Cmd':['app']}};mf=[{'RepoTags':['pv-growth-app:'+tag],'Config':'config.json','Layers':['layer.tar']}]
   with tarfile.open(p,'w') as t:
    for name,data in [('manifest.json',json.dumps(mf).encode()),('config.json',json.dumps(cfg).encode()),('layer.tar',layer)]:
     entry=tarfile.TarInfo(name);entry.size=len(data);t.addfile(entry,io.BytesIO(data))
   first=[{'Id':'old','RootFS':{'Layers':[diff]},'Config':{'Cmd':['app']}}]
   changed=[{'Id':'new','RootFS':{'Layers':[diff]},'Config':{'Cmd':['different']}}]
   with patch.object(m,'checked',side_effect=[json.dumps(first),json.dumps(changed)]),patch.object(m.guard,'open_file',return_value=False):
    self.assertTrue(m.archive_complete(p,tag));self.assertFalse(m.archive_complete(p,tag))

class ClientUdp(unittest.TestCase):
 def test_only_declared_outbound_client_ports_are_volatile(self):
  f='UNCONN 0 0 0.0.0.0:55425 0.0.0.0:* users:(("frpc",pid=10,fd=1))'.split()
  with patch.object(m,'CONFIG',{'udp_client_names':['frpc'],'protected_udp_ports':[1194]}):
   self.assertTrue(m.volatile_udp_client(f))
   protected=list(f);protected[3]='0.0.0.0:1194';self.assertFalse(m.volatile_udp_client(protected))
   other=list(f);other[-1]=other[-1].replace('frpc','openvpn');self.assertFalse(m.volatile_udp_client(other))

class NetworkObservation(unittest.TestCase):
 def test_runtime_routes_and_udp_clients_are_observed_without_masking_configuration_changes(self):
  cfg={'critical_units':[],'running_containers':[],'http_checks':[],'sqlite_checks':[],'native_checks':[]}
  with patch.object(m,'CONFIG',cfg),patch.object(m.shutil,'which',return_value=None),patch.object(m,'listeners',side_effect=[([('tcp','LISTEN','*:443','*:*'),('udp','UNCONN','*:55555','*:*',())],{}),([('tcp','LISTEN','*:443','*:*'),('udp','UNCONN','*:44444','*:*',())],{})]),patch.object(m,'checked',side_effect=['dynamic route A','same firewall','dynamic route B','same firewall']),patch.object(m,'network_configuration',return_value={'netplan':'unchanged'}):
   a=m.snapshot();b=m.snapshot()
   self.assertEqual(a['identity'],b['identity'])
   self.assertNotEqual(a['route_observation'],b['route_observation'])
   self.assertNotEqual(a['udp_observation'],b['udp_observation'])
  # Production configuration remains a hard guard, independent of traffic telemetry.
  self.assertEqual(a['identity']['network_configuration'],{'netplan':'unchanged'})
