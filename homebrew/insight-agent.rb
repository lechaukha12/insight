class InsightAgent < Formula
  desc "Insight System Agent — cross-platform system resource monitoring"
  homepage "https://github.com/lechaukha12/insight"
  url "https://github.com/lechaukha12/insight/archive/refs/tags/v5.0.6.tar.gz"
  sha256 ""  # Update after creating the release tag
  license "MIT"
  version "5.0.6"

  depends_on "python@3.11"

  def install
    # Install Python dependencies
    system "python3", "-m", "pip", "install", "--prefix=#{prefix}",
           "requests>=2.31.0", "psutil>=5.9.0"

    # Install the agent script
    libexec.install "agents/system-agent/agent.py" => "insight-agent.py"

    # Create wrapper script
    (bin/"insight-agent").write <<~EOS
      #!/bin/bash
      export PYTHONPATH="#{lib}/python3.11/site-packages:$PYTHONPATH"
      exec "#{Formula["python@3.11"].opt_bin}/python3" "#{libexec}/insight-agent.py" "$@"
    EOS
  end

  def caveats
    <<~EOS
      Insight System Agent has been installed!

      Configuration (environment variables):
        INSIGHT_CORE_URL   API server URL (default: http://localhost:8080)
        AGENT_TOKEN        Agent authentication token (required)
        AGENT_ID           Agent identifier (default: system-agent-<hostname>)
        AGENT_NAME         Display name (default: System Agent (<hostname>))
        SCAN_INTERVAL      Monitoring interval in seconds (default: 30)

      Quick start:
        export INSIGHT_CORE_URL="http://your-api-server:8080"
        export AGENT_TOKEN="your-agent-token"
        insight-agent

      To run as a background service:
        brew services start insight-agent
    EOS
  end

  service do
    run [opt_bin/"insight-agent"]
    keep_alive true
    log_path var/"log/insight-agent.log"
    error_log_path var/"log/insight-agent-error.log"
    environment_variables INSIGHT_CORE_URL: "http://localhost:8080",
                          AGENT_TOKEN: "",
                          SCAN_INTERVAL: "30"
    working_dir var/"insight-agent"
  end

  test do
    assert_match "Insight System Agent", shell_output("#{bin}/insight-agent --help 2>&1", 0)
  end
end
