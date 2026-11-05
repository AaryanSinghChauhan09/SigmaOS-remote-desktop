#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RemoteProtocol { Vnc, Rdp, Spice }

#[derive(Debug)]
pub struct RemoteSessionConfig {
    pub protocol: RemoteProtocol,
    pub host: String,
    pub port: u16,
    pub enable_audio: bool,
}

impl RemoteSessionConfig {
    pub fn new(proto: RemoteProtocol, host: &str, port: u16) -> Self {
        Self { protocol: proto, host: host.into(), port, enable_audio: true }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_remote_session_config_aaa() {
        // Arrange & Act
        let cfg = RemoteSessionConfig::new(RemoteProtocol::Rdp, "192.168.1.150", 3389);
        // Assert
        assert_eq!(cfg.protocol, RemoteProtocol::Rdp);
        assert_eq!(cfg.port, 3389);
        assert!(cfg.enable_audio);
    }
}
