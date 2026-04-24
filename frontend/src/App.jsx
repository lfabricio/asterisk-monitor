import { useState, useEffect, useCallback } from 'react';
import './App.css';

const API_BASE_URL = 'http://localhost:8000/api';

function App() {
  const [systemInfo, setSystemInfo] = useState({ version: '--', startup: '--', status: 'loading' });
  const [ramalInfo, setRamalInfo] = useState({ status: 'loading', channels: '-', isOnline: false });
  const [lastUpdate, setLastUpdate] = useState('--:--:--');
  const [isSpinning, setIsSpinning] = useState(false);
  const [globalStatus, setGlobalStatus] = useState('loading');

  const formatStartupTime = (dateString) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
    } catch {
      return dateString;
    }
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
      const ramRes = await fetch(`${API_BASE_URL}/monitor/3770`);
      if (ramRes.ok) {
        const ramData = await ramRes.json();
        const isOnline = ramData.status?.toLowerCase() !== 'offline';
        setRamalInfo({
          status: ramData.status?.toUpperCase() || 'UNKNOWN',
          channels: ramData.canais_ativos || 0,
          isOnline
        });
      } else {
        throw new Error('Ramal fetch failed');
      }
    } catch (err) {
      setRamalInfo({ status: 'ERRO', channels: '-', isOnline: false });
    }

    setGlobalStatus(sysOk ? 'online' : 'offline');
    setLastUpdate(new Date().toLocaleTimeString('pt-BR'));
    
    setTimeout(() => setIsSpinning(false), 500);
  }, []);

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 10000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

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

        <section className="dashboard">
          <article className="card glass">
            <div className="card-header">
              <h2>Servidor Asterisk</h2>
              <span className={`badge ${systemInfo.status}`}>
                {systemInfo.status === 'loading' ? 'Conectando...' : systemInfo.status.toUpperCase()}
              </span>
            </div>
            <div className="card-body">
              <div className="stat-group">
                <div className="stat">
                  <span className="label">Versão do Core</span>
                  <span className="value">{systemInfo.version}</span>
                </div>
                <div className="stat">
                  <span className="label">Último Startup</span>
                  <span className="value">{systemInfo.startup}</span>
                </div>
              </div>
            </div>
          </article>

          <article className="card glass highlight">
            <div className="card-header">
              <h2>Ramal Monitorado (3770)</h2>
              <span className={`badge ${ramalInfo.status === 'loading' ? 'loading' : (ramalInfo.isOnline ? 'online' : 'offline')}`}>
                {ramalInfo.status === 'loading' ? 'Consultando...' : ramalInfo.status}
              </span>
            </div>
            <div className="card-body">
              <div className="stat-group">
                <div className="stat">
                  <span className="label">Estado Atual</span>
                  <span className={`value status-text ${ramalInfo.isOnline ? 'text-success' : 'text-danger'}`}>
                    {ramalInfo.status === 'loading' ? '--' : (ramalInfo.isOnline ? 'Registrado' : 'Desconectado')}
                  </span>
                </div>
                <div className="stat">
                  <span className="label">Canais Ativos</span>
                  <span className="value giant">{ramalInfo.channels}</span>
                </div>
              </div>
            </div>
          </article>
        </section>
        
        <footer>
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
          <p className="last-update">Sincronizado às: <span>{lastUpdate}</span></p>
        </footer>
      </main>
    </div>
  );
}

export default App;
