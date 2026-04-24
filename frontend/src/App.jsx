import { useState, useEffect, useCallback } from 'react';
import './App.css';

const API_BASE_URL = 'http://localhost:8000/api';

function App() {
  const [systemInfo, setSystemInfo] = useState({ version: '--', startup: '--', status: 'loading' });
  const [ramais, setRamais] = useState([]);
  const [globalChannels, setGlobalChannels] = useState(0);
  const [activeChannelsList, setActiveChannelsList] = useState([]);
  const [lastUpdate, setLastUpdate] = useState('--:--:--');
  const [isSpinning, setIsSpinning] = useState(false);
  const [globalStatus, setGlobalStatus] = useState('loading');
  const [isAutoRefresh, setIsAutoRefresh] = useState(true);

  const formatStartupTime = (dateString) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
    } catch {
      return dateString;
    }
  };

  const formatDuration = (creationTimeString) => {
    if (!creationTimeString) return '--:--';
    try {
      const start = new Date(creationTimeString);
      const now = new Date();
      const diffMs = Math.max(0, now - start);
      const diffMins = Math.floor(diffMs / 60000);
      const diffSecs = Math.floor((diffMs % 60000) / 1000);
      return `${diffMins.toString().padStart(2, '0')}:${diffSecs.toString().padStart(2, '0')}`;
    } catch {
      return '--:--';
    }
  };

  const groupChannels = (channels) => {
    const grouped = [];
    const usedIds = new Set();

    for (const ch of channels) {
      if (usedIds.has(ch.id)) continue;

      const orig1 = ch.caller?.number || '';
      const dest1 = ch.connected?.number || ch.dialplan?.exten || '';

      const partner = channels.find(p => {
        if (p.id === ch.id || usedIds.has(p.id)) return false;
        const orig2 = p.caller?.number || '';
        const dest2 = p.connected?.number || p.dialplan?.exten || '';
        return (orig1 === dest2 && dest1 === orig2);
      });

      if (partner) {
        usedIds.add(ch.id);
        usedIds.add(partner.id);
        grouped.push({
          id: `${ch.id}-${partner.id}`,
          isGrouped: true,
          origem: orig1,
          origemName: ch.caller?.name,
          destino: dest1,
          destinoName: partner.caller?.name,
          state: ch.state?.toLowerCase() === 'up' && partner.state?.toLowerCase() === 'up' ? 'Up' : ch.state,
          creationtime: ch.creationtime,
          rawNames: [ch.name?.split('-')[0], partner.name?.split('-')[0]].filter(Boolean)
        });
      } else {
        usedIds.add(ch.id);
        grouped.push({
          id: ch.id,
          isGrouped: false,
          origem: orig1,
          origemName: ch.caller?.name,
          destino: dest1,
          destinoName: ch.connected?.name,
          state: ch.state,
          creationtime: ch.creationtime,
          rawNames: [ch.name?.split('-')[0]].filter(Boolean)
        });
      }
    }
    return grouped;
  };

  const fetchDashboardData = useCallback(async () => {
    setIsSpinning(true);
    let sysOk = false;

    try {
      const sysRes = await fetch(`${API_BASE_URL}/asterisk/info`);
      if (sysRes.ok) {
        const sysData = await sysRes.json();
        setSystemInfo({
          version: sysData.system?.version || '--',
          startup: formatStartupTime(sysData.status?.startup_time),
          status: 'online'
        });
        sysOk = true;
      } else {
        throw new Error('System fetch failed');
      }
    } catch (err) {
      setSystemInfo({ version: 'Indisponível', startup: '--', status: 'offline' });
    }

    try {
      const ramRes = await fetch(`${API_BASE_URL}/monitor/ramais`);
      if (ramRes.ok) {
        const ramData = await ramRes.json();
        setRamais(ramData);
      } else {
        throw new Error('Ramais fetch failed');
      }
    } catch (err) {
      setRamais([]);
    }

    try {
      const chanRes = await fetch(`${API_BASE_URL}/monitor/channels`);
      if (chanRes.ok) {
        const chanData = await chanRes.json();
        setGlobalChannels(chanData.total_channels || 0);
        setActiveChannelsList(chanData.raw_data || []);
      }
    } catch (err) {
      setGlobalChannels(0);
      setActiveChannelsList([]);
    }

    setGlobalStatus(sysOk ? 'online' : 'offline');
    setLastUpdate(new Date().toLocaleTimeString('pt-BR'));

    setTimeout(() => setIsSpinning(false), 500);
  }, []);

  useEffect(() => {
    fetchDashboardData();
    if (!isAutoRefresh) return;
    const interval = setInterval(fetchDashboardData, 10000);
    return () => clearInterval(interval);
  }, [fetchDashboardData, isAutoRefresh]);

  // Aggregated Stats
  const totalRamais = ramais.length;
  const ramaisOnline = ramais.filter(r => r.status.toLowerCase() !== 'offline').length;
  const totalCanaisRamais = ramais.reduce((acc, curr) => acc + curr.canais_ativos, 0);

  const groupedActiveChannels = groupChannels(activeChannelsList);

  return (
    <div className="app-container">
      <div className="background-mesh">
        <div className="blob blob-1"></div>
        <div className="blob blob-2"></div>
      </div>

      <main className="content-wrapper">
        <header>
          <div className="logo-wrapper">
            <div className={`status-indicator ${globalStatus}`}></div>
            <h1>Asterisk Monitor</h1>
          </div>
          <p>Painel de Controle em Tempo Real</p>
        </header>

        {/* Global Summary */}
        <section className="dashboard" style={{ marginBottom: '2rem' }}>
          <article className="card glass" style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '1.2rem' }}>
            <h2 style={{ fontSize: '1.2rem', fontWeight: '500', margin: 0, color: 'var(--text-main)', display: 'flex', justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
              <span>Total de Ramais: <strong style={{ color: 'var(--text-main)' }}>{totalRamais}</strong></span>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>|</span>
              <span>Ramais Online: <strong className="text-success">{ramaisOnline}</strong></span>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>|</span>
              <span>Canais Ativos (Ramais): <strong style={{ color: totalCanaisRamais > 0 ? 'var(--warning)' : 'inherit' }}>{totalCanaisRamais}</strong></span>
              <span style={{ color: 'rgba(255,255,255,0.2)' }}>|</span>
              <span>Canais Ativos (PBX Inteiro): <strong style={{ color: globalChannels > 0 ? 'var(--warning)' : 'inherit' }}>{globalChannels}</strong></span>
            </h2>
          </article>
        </section>

        {/* Active Channels Table */}
        {activeChannelsList.length > 0 && (
          <section style={{ marginBottom: '2rem', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem' }}>
              <h2 style={{ fontSize: '1.4rem', fontWeight: '600' }}>Canais de Voz Ativos</h2>
            </div>
            <div className="card glass" style={{ overflowX: 'auto', padding: '0' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', backgroundColor: 'rgba(255,255,255,0.05)' }}>
                    <th style={{ padding: '1rem', fontWeight: '600' }}>Canal</th>
                    <th style={{ padding: '1rem', fontWeight: '600' }}>Origem</th>
                    <th style={{ padding: '1rem', fontWeight: '600' }}>Destino</th>
                    <th style={{ padding: '1rem', fontWeight: '600' }}>Status</th>
                    <th style={{ padding: '1rem', fontWeight: '600' }}>Duração</th>
                  </tr>
                </thead>
                <tbody>
                  {groupedActiveChannels.map(ch => (
                    <tr key={ch.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '1rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                        {ch.rawNames.join(' ↔ ') || ch.id}
                      </td>
                      <td style={{ padding: '1rem', fontWeight: '500' }}>
                        {ch.origem || 'Desconhecido'}
                        {ch.origemName && ch.origemName !== ch.origem ? ` (${ch.origemName})` : ''}
                      </td>
                      <td style={{ padding: '1rem', fontWeight: '500' }}>
                        {ch.destino || 'Desconhecido'}
                        {ch.destinoName && ch.destinoName !== ch.destino ? ` (${ch.destinoName})` : ''}
                      </td>
                      <td style={{ padding: '1rem' }}>
                        <span className={`badge ${ch.state?.toLowerCase() === 'up' ? 'online' : 'offline'}`} style={{ fontSize: '0.75rem', padding: '3px 8px' }}>
                          {ch.state || 'Desconhecido'}
                        </span>
                      </td>
                      <td style={{ padding: '1rem', fontFamily: 'monospace', fontSize: '1.1rem', color: 'var(--accent-color)' }}>
                        {formatDuration(ch.creationtime)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Ramais Grid */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: '600' }}>Todos os Ramais</h2>
        </div>

        <section className="dashboard" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem' }}>
          {ramais.length === 0 ? (
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
              Nenhum ramal numérico encontrado.
            </div>
          ) : (
            ramais.map((ramal) => {
              const isOnline = ramal.status.toLowerCase() !== 'offline';
              return (
                <article key={ramal.ramal} className="card glass highlight" style={{ padding: '1rem' }}>
                  <div className="card-header" style={{ marginBottom: '0.8rem', paddingBottom: '0.5rem' }}>
                    <h2 style={{ fontSize: '1.1rem' }}>Ramal {ramal.ramal}</h2>
                    <span className={`badge ${isOnline ? 'online' : 'offline'}`} style={{ fontSize: '0.65rem', padding: '2px 6px' }}>
                      {ramal.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="card-body">
                    <div className="stat-group" style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div className="stat" style={{ gap: '0.2rem' }}>
                        <span className="label" style={{ fontSize: '0.75rem' }}>Estado</span>
                        <span className={`value status-text ${isOnline ? 'text-success' : 'text-danger'}`} style={{ fontSize: '0.9rem' }}>
                          {isOnline ? 'Registrado' : 'Offline'}
                        </span>
                      </div>
                      <div className="stat" style={{ alignItems: 'flex-end', gap: '0.2rem' }}>
                        <span className="label" style={{ fontSize: '0.75rem' }}>Canais</span>
                        <span className="value giant" style={{ fontSize: '1.5rem' }}>{ramal.canais_ativos}</span>
                      </div>
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </section>

        <footer>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', justifyContent: 'center' }}>
              <button
                onClick={fetchDashboardData}
                className={`btn-refresh ${isSpinning ? 'spinning' : ''}`}
                disabled={isSpinning}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"></path>
                  <path d="M21 3v5h-5"></path>
                </svg>
                Atualizar Agora
              </button>

              <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', background: 'rgba(255,255,255,0.05)', padding: '10px 16px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)', transition: 'all 0.2s ease' }}>
                <input
                  type="checkbox"
                  checked={isAutoRefresh}
                  onChange={(e) => setIsAutoRefresh(e.target.checked)}
                  style={{ cursor: 'pointer', width: '1.2rem', height: '1.2rem', accentColor: 'var(--accent-color)' }}
                />
                <span style={{ fontSize: '0.95rem', color: 'var(--text-main)', fontWeight: '500' }}>
                  Auto Update (10s)
                </span>
              </label>

            </div>
            <p className="last-update">Sincronizado às: <span>{lastUpdate}</span></p>
          </div>
        </footer>
      </main>
    </div>
  );
}

export default App;
