import React from "react";
import { Link } from "react-router-dom";

type WorkspaceWelcomeProps = {
  onContinue: () => void;
  showHint: boolean;
};

const WorkspaceWelcome: React.FC<WorkspaceWelcomeProps> = ({ onContinue, showHint }) => {
  return (
    <div className="workspace-welcome">
      <p className="workspace-welcome__eyebrow">What would you like to explore today?</p>
      <div className="workspace-welcome__actions">
        <Link to="/app/case" className="button primary">
          Start a New Case
        </Link>
        <button type="button" className="button ghost" onClick={onContinue}>
          Continue a Case
        </button>
      </div>
      {showHint ? (
        <p className="workspace-welcome__hint">Select a case from the sidebar to continue.</p>
      ) : null}
    </div>
  );
};

export default WorkspaceWelcome;
